import asyncio
from copy import deepcopy
from typing import Any, cast

from langgraph.types import Command

from novel_translation_backend.constants.workflow_status import (
    WORKFLOW_STATUS_ERROR,
    WORKFLOW_STATUS_FINAL_REVIEW,
    WORKFLOW_STATUS_GLOSSARY_REVIEW,
)
from novel_translation_backend.graph.graph import graph
from novel_translation_backend.graph.state import WorkflowState


state_store: dict[str, WorkflowState] = {}

_state_store_lock = asyncio.Lock()
_active_tasks: set[asyncio.Task[None]] = set()


async def run_graph(
    workflow_id: str,
    graph_input: WorkflowState | Command[Any],
) -> None:
    try:
        config: Any = {"configurable": {"thread_id": workflow_id}}
        await graph.ainvoke(graph_input, config=config)
        snapshot = await graph.aget_state(config)

        latest_state = cast(WorkflowState, deepcopy(snapshot.values))
        if "hitl_glossary" in snapshot.next:
            latest_state["status"] = WORKFLOW_STATUS_GLOSSARY_REVIEW
        elif "hitl_final" in snapshot.next:
            latest_state["status"] = WORKFLOW_STATUS_FINAL_REVIEW

        async with _state_store_lock:
            state_store[workflow_id] = latest_state
    except Exception as exc:
        async with _state_store_lock:
            state_store[workflow_id]["status"] = WORKFLOW_STATUS_ERROR
            state_store[workflow_id]["error_detail"] = str(exc)
        raise


async def start_graph(
    workflow_id: str,
    initial_state: WorkflowState,
) -> None:
    async with _state_store_lock:
        state_store[workflow_id] = initial_state

    _schedule_graph(workflow_id, initial_state)


async def resume_graph(workflow_id: str, resume_payload: Any) -> None:
    async with _state_store_lock:
        workflow_state = state_store.get(workflow_id)
        if workflow_state is None:
            raise KeyError(f"Workflow not found: {workflow_id}")
        if workflow_state["status"] not in {
            WORKFLOW_STATUS_GLOSSARY_REVIEW,
            WORKFLOW_STATUS_FINAL_REVIEW,
        }:
            raise RuntimeError(f"Workflow is not paused for review: {workflow_id}")
        state_update = deepcopy(workflow_state)

    _schedule_graph(
        workflow_id,
        Command(update=state_update, resume=resume_payload),
    )


async def get_state(workflow_id: str) -> WorkflowState | None:
    async with _state_store_lock:
        state = state_store.get(workflow_id)
        return deepcopy(state) if state is not None else None


def _handle_task_done(task: asyncio.Task[None]) -> None:
    _active_tasks.discard(task)

    if not task.cancelled():
        task.exception()


def _schedule_graph(
    workflow_id: str,
    graph_input: WorkflowState | Command[Any],
) -> None:
    task = asyncio.create_task(run_graph(workflow_id, graph_input))
    _active_tasks.add(task)
    task.add_done_callback(_handle_task_done)
