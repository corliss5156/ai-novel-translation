from collections.abc import Mapping
from typing import Any

from langgraph.types import interrupt

from novel_translation_backend.constants.review import (
    REVIEW_ACTION_APPROVE,
    REVIEW_ACTION_REVISE,
    REVIEW_TYPE_FINAL,
)
from novel_translation_backend.constants.workflow_status import (
    WORKFLOW_STATUS_FINAL_REVIEW,
    WORKFLOW_STATUS_REVISE,
)
from novel_translation_backend.graph.state import WorkflowState


def hitl_final_node(state: WorkflowState) -> WorkflowState:
    state["status"] = WORKFLOW_STATUS_FINAL_REVIEW

    decision = interrupt(
        {
            "decision_type": REVIEW_TYPE_FINAL,
            "workflow_id": state["workflow_id"],
            "edited_text": state["edited_text"],
        }
    )
    action = _review_action(decision)
    if action == REVIEW_ACTION_REVISE:
        feedback = state["editor_feedback"]
        if feedback is None or not feedback.strip():
            raise ValueError("editor_feedback must be non-empty before revision")
        state["status"] = WORKFLOW_STATUS_REVISE
        return state
    if action != REVIEW_ACTION_APPROVE:
        raise ValueError(f"Unsupported final review action: {action}")

    final_text = state["final_text"]
    if final_text is None or not final_text.strip():
        raise ValueError("final_text must be non-empty before final approval")

    return state


def _review_action(decision: Any) -> str:
    if not isinstance(decision, Mapping):
        raise ValueError("Final review decision must be an object")

    action = decision.get("action")
    if not isinstance(action, str):
        raise ValueError("Final review decision requires an action")
    return action
