from collections.abc import Mapping
from typing import Any

from langgraph.types import interrupt

from novel_translation_backend.constants.review import (
    REVIEW_ACTION_APPROVE,
    REVIEW_TYPE_GLOSSARY,
)
from novel_translation_backend.constants.workflow_status import (
    WORKFLOW_STATUS_GLOSSARY_REVIEW,
)
from novel_translation_backend.graph.state import WorkflowState


def hitl_glossary_node(state: WorkflowState) -> WorkflowState:
    state["status"] = WORKFLOW_STATUS_GLOSSARY_REVIEW

    decision = interrupt(
        {
            "decision_type": REVIEW_TYPE_GLOSSARY,
            "workflow_id": state["workflow_id"],
            "glossary_terms": [
                term for term in state["glossary_terms"] if term["is_new"]
            ],
        }
    )
    action = _review_action(decision)
    if action != REVIEW_ACTION_APPROVE:
        raise ValueError(f"Unsupported glossary review action: {action}")

    return state


def _review_action(decision: Any) -> str:
    if not isinstance(decision, Mapping):
        raise ValueError("Glossary review decision must be an object")

    action = decision.get("action")
    if not isinstance(action, str):
        raise ValueError("Glossary review decision requires an action")
    return action
