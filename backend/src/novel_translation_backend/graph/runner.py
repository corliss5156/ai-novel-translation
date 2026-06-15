import asyncio
from copy import deepcopy
from typing import Any, cast

from langgraph.types import Command

from novel_translation_backend.constants.glossary_status import (
    GLOSSARY_STATUS_APPROVED,
    GLOSSARY_STATUS_REJECTED,
)
from novel_translation_backend.constants.review import (
    REVIEW_ACTION_APPROVE,
    REVIEW_ACTION_REJECT,
    REVIEW_ACTION_REVISE,
)
from novel_translation_backend.constants.workflow_status import (
    WORKFLOW_ERROR_CODE_SAVE_CONFLICT,
    WORKFLOW_ERROR_CODE_SAVE_FAILED,
    WORKFLOW_ERROR_STAGE_COMPLETE,
    WORKFLOW_STATUS_COMPLETE,
    WORKFLOW_STATUS_EDITING,
    WORKFLOW_STATUS_ERROR,
    WORKFLOW_STATUS_FINAL_REVIEW,
    WORKFLOW_STATUS_GLOSSARY_REVIEW,
    WORKFLOW_STATUS_SAVING,
    WORKFLOW_STATUS_TRANSLATING,
)
from novel_translation_backend.graph.graph import graph
from novel_translation_backend.graph.nodes.complete import complete_node
from novel_translation_backend.graph.state import GlossaryTerm, WorkflowState
from novel_translation_backend.storage.s3_chapters import (
    ChapterSaveConflictError,
    ChapterSaveError,
)


state_store: dict[str, WorkflowState] = {}

_state_store_lock = asyncio.Lock()
_active_tasks: set[asyncio.Task[None]] = set()
_tasks_by_workflow: dict[str, set[asyncio.Task[None]]] = {}


class WorkflowAlreadyRunningError(RuntimeError):
    pass


class WorkflowNotFoundError(KeyError):
    pass


class WorkflowNotPausedForGlossaryReviewError(RuntimeError):
    pass


class WorkflowNotPausedForFinalReviewError(RuntimeError):
    pass


class InvalidGlossaryDecisionsError(ValueError):
    pass


class InvalidFinalReviewDecisionError(ValueError):
    pass


class InvalidEditorReviewFeedbackError(ValueError):
    pass


class WorkflowSaveNotRetryableError(RuntimeError):
    pass


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
            if workflow_id in state_store:
                state_store[workflow_id] = latest_state
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        async with _state_store_lock:
            workflow_state = state_store.get(workflow_id)
            if workflow_state is not None:
                workflow_state["status"] = WORKFLOW_STATUS_ERROR
                workflow_state["error_detail"] = str(exc)
                if isinstance(exc, ChapterSaveConflictError):
                    workflow_state["error_stage"] = WORKFLOW_ERROR_STAGE_COMPLETE
                    workflow_state["error_code"] = WORKFLOW_ERROR_CODE_SAVE_CONFLICT
                elif isinstance(exc, ChapterSaveError):
                    workflow_state["error_stage"] = WORKFLOW_ERROR_STAGE_COMPLETE
                    workflow_state["error_code"] = WORKFLOW_ERROR_CODE_SAVE_FAILED
                else:
                    workflow_state["error_stage"] = None
                    workflow_state["error_code"] = None
        raise


async def start_graph(
    workflow_id: str,
    initial_state: WorkflowState,
) -> None:
    async with _state_store_lock:
        for workflow_state in state_store.values():
            if (
                workflow_state["novel_name"] == initial_state["novel_name"]
                and workflow_state["chapter_number"] == initial_state["chapter_number"]
                and workflow_state["status"]
                not in {WORKFLOW_STATUS_COMPLETE, WORKFLOW_STATUS_ERROR}
            ):
                raise WorkflowAlreadyRunningError(
                    "A workflow is already running for this novel and chapter"
                )
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


async def submit_glossary_review(
    workflow_id: str,
    decisions: dict[str, tuple[str, str | None]],
    suggestions: dict[str, str],
) -> None:
    async with _state_store_lock:
        workflow_state = state_store.get(workflow_id)
        if workflow_state is None:
            raise WorkflowNotFoundError(workflow_id)
        if workflow_state["status"] != WORKFLOW_STATUS_GLOSSARY_REVIEW:
            raise WorkflowNotPausedForGlossaryReviewError(workflow_id)

        all_terms_by_key = {
            term["chinese"]: term for term in workflow_state["glossary_terms"]
        }
        new_terms_by_key = {
            term_key: term
            for term_key, term in all_terms_by_key.items()
            if term["is_new"]
        }
        if set(decisions) != set(new_terms_by_key):
            raise InvalidGlossaryDecisionsError(
                "Decisions must include every new glossary term exactly once"
            )
        if set(suggestions) & set(all_terms_by_key):
            raise InvalidGlossaryDecisionsError(
                "Suggestions must not duplicate existing glossary terms"
            )
        if any(
            not term_key.strip() or not approved_english.strip()
            for term_key, approved_english in suggestions.items()
        ):
            raise InvalidGlossaryDecisionsError(
                "Suggestions require non-empty Chinese and approved English values"
            )
        if any(
            action not in {REVIEW_ACTION_APPROVE, REVIEW_ACTION_REJECT}
            for action, _ in decisions.values()
        ):
            raise InvalidGlossaryDecisionsError(
                "Glossary decision action must be approve or reject"
            )
        if any(
            action == REVIEW_ACTION_APPROVE
            and (approved_english is None or not approved_english.strip())
            for action, approved_english in decisions.values()
        ):
            raise InvalidGlossaryDecisionsError(
                "Approved glossary terms require approved English values"
            )

        for term_key, (action, approved_english) in decisions.items():
            term = new_terms_by_key[term_key]
            if action == REVIEW_ACTION_APPROVE:
                term["status"] = GLOSSARY_STATUS_APPROVED
                term["approved_english"] = approved_english
            else:
                term["status"] = GLOSSARY_STATUS_REJECTED
                term["approved_english"] = None

        workflow_state["glossary_terms"].extend(
            GlossaryTerm(
                chinese=term_key,
                proposed_english=approved_english,
                description="",
                approved_english=approved_english,
                status=GLOSSARY_STATUS_APPROVED,
                is_new=True,
            )
            for term_key, approved_english in suggestions.items()
        )
        workflow_state["status"] = WORKFLOW_STATUS_TRANSLATING
        state_update = deepcopy(workflow_state)
        _schedule_graph(
            workflow_id,
            Command(update=state_update, resume={"action": REVIEW_ACTION_APPROVE}),
        )


async def submit_final_review(
    workflow_id: str,
    final_text: str,
) -> None:
    async with _state_store_lock:
        workflow_state = state_store.get(workflow_id)
        if workflow_state is None:
            raise WorkflowNotFoundError(workflow_id)
        if workflow_state["status"] != WORKFLOW_STATUS_FINAL_REVIEW:
            raise WorkflowNotPausedForFinalReviewError(workflow_id)

        if not final_text.strip():
            raise InvalidFinalReviewDecisionError(
                "Final text must be a non-empty string"
            )

        workflow_state["final_text"] = final_text
        workflow_state["status"] = WORKFLOW_STATUS_SAVING
        state_update = deepcopy(workflow_state)
        _schedule_graph(
            workflow_id,
            Command(
                update=state_update,
                resume={"action": REVIEW_ACTION_APPROVE},
            ),
        )


async def submit_editor_review(
    workflow_id: str,
    feedback: str,
) -> None:
    async with _state_store_lock:
        workflow_state = state_store.get(workflow_id)
        if workflow_state is None:
            raise WorkflowNotFoundError(workflow_id)
        if workflow_state["status"] != WORKFLOW_STATUS_FINAL_REVIEW:
            raise WorkflowNotPausedForFinalReviewError(workflow_id)
        if len(feedback.strip()) < 10:
            raise InvalidEditorReviewFeedbackError(
                "Editor revision feedback must contain at least 10 characters"
            )

        workflow_state["editor_feedback"] = feedback.strip()
        workflow_state["status"] = WORKFLOW_STATUS_EDITING
        state_update = deepcopy(workflow_state)
        _schedule_graph(
            workflow_id,
            Command(
                update=state_update,
                resume={"action": REVIEW_ACTION_REVISE},
            ),
        )


async def retry_final_save(workflow_id: str) -> None:
    async with _state_store_lock:
        workflow_state = state_store.get(workflow_id)
        if workflow_state is None:
            raise WorkflowNotFoundError(workflow_id)
        if (
            workflow_state["status"] != WORKFLOW_STATUS_ERROR
            or workflow_state["error_stage"] != WORKFLOW_ERROR_STAGE_COMPLETE
            or workflow_state["error_code"] != WORKFLOW_ERROR_CODE_SAVE_FAILED
        ):
            raise WorkflowSaveNotRetryableError(workflow_id)

        final_text = workflow_state["final_text"]
        if final_text is None or not final_text.strip():
            raise WorkflowSaveNotRetryableError(workflow_id)

        workflow_state["status"] = WORKFLOW_STATUS_SAVING
        state_update = deepcopy(workflow_state)

    try:
        completed_state = complete_node(state_update)
    except ChapterSaveConflictError as exc:
        async with _state_store_lock:
            workflow_state = state_store.get(workflow_id)
            if workflow_state is not None:
                workflow_state["status"] = WORKFLOW_STATUS_ERROR
                workflow_state["error_detail"] = str(exc)
                workflow_state["error_stage"] = WORKFLOW_ERROR_STAGE_COMPLETE
                workflow_state["error_code"] = WORKFLOW_ERROR_CODE_SAVE_CONFLICT
        raise
    except ChapterSaveError as exc:
        async with _state_store_lock:
            workflow_state = state_store.get(workflow_id)
            if workflow_state is not None:
                workflow_state["status"] = WORKFLOW_STATUS_ERROR
                workflow_state["error_detail"] = str(exc)
                workflow_state["error_stage"] = WORKFLOW_ERROR_STAGE_COMPLETE
                workflow_state["error_code"] = WORKFLOW_ERROR_CODE_SAVE_FAILED
        raise

    async with _state_store_lock:
        if workflow_id in state_store:
            state_store[workflow_id] = completed_state


async def get_state(workflow_id: str) -> WorkflowState | None:
    async with _state_store_lock:
        state = state_store.get(workflow_id)
        return deepcopy(state) if state is not None else None


async def kill_workflow(workflow_id: str) -> None:
    async with _state_store_lock:
        if workflow_id not in state_store:
            raise WorkflowNotFoundError(workflow_id)

        del state_store[workflow_id]
        tasks = list(_tasks_by_workflow.pop(workflow_id, set()))

    for task in tasks:
        task.cancel()


def _handle_task_done(workflow_id: str, task: asyncio.Task[None]) -> None:
    _active_tasks.discard(task)
    workflow_tasks = _tasks_by_workflow.get(workflow_id)
    if workflow_tasks is not None:
        workflow_tasks.discard(task)
        if not workflow_tasks:
            _tasks_by_workflow.pop(workflow_id, None)

    if not task.cancelled():
        task.exception()


def _schedule_graph(
    workflow_id: str,
    graph_input: WorkflowState | Command[Any],
) -> None:
    task = asyncio.create_task(run_graph(workflow_id, graph_input))
    _active_tasks.add(task)
    _tasks_by_workflow.setdefault(workflow_id, set()).add(task)
    task.add_done_callback(lambda done_task: _handle_task_done(workflow_id, done_task))
