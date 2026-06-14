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
        state["editor_feedback"] = _revision_feedback(decision)
        state["status"] = WORKFLOW_STATUS_REVISE
    elif action == REVIEW_ACTION_APPROVE:
        edited_text = state["edited_text"]
        if edited_text is None or not edited_text.strip():
            raise ValueError("edited_text must be non-empty before final approval")
        state["final_text"] = edited_text
    else:
        raise ValueError(f"Unsupported final review action: {action}")

    return state


def _review_action(decision: Any) -> str:
    if not isinstance(decision, Mapping):
        raise ValueError("Final review decision must be an object")

    action = decision.get("action")
    if not isinstance(action, str):
        raise ValueError("Final review decision requires an action")
    return action


def _revision_feedback(decision: Any) -> str:
    if not isinstance(decision, Mapping):
        raise ValueError("Final review decision must be an object")

    feedback = decision.get("feedback")
    if not isinstance(feedback, str) or not feedback.strip():
        raise ValueError("Revision feedback must be a non-empty string")
    return feedback
