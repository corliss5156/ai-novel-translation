import asyncio
from copy import deepcopy

from novel_translation_backend.constants.workflow_status import WORKFLOW_STATUS_ERROR
from novel_translation_backend.graph.graph import graph
from novel_translation_backend.graph.state import WorkflowState


state_store: dict[str, WorkflowState] = {}

_state_store_lock = asyncio.Lock()
_active_tasks: set[asyncio.Task[None]] = set()


async def run_graph(workflow_id: str, initial_state: WorkflowState) -> None:
    try:
        await graph.ainvoke(initial_state, config={"thread_id": workflow_id})
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

    task = asyncio.create_task(run_graph(workflow_id, initial_state))
    _active_tasks.add(task)
    task.add_done_callback(_handle_task_done)


async def get_state(workflow_id: str) -> WorkflowState | None:
    async with _state_store_lock:
        state = state_store.get(workflow_id)
        return deepcopy(state) if state is not None else None


def _handle_task_done(task: asyncio.Task[None]) -> None:
    _active_tasks.discard(task)

    if not task.cancelled():
        task.exception()
