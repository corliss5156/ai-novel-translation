from typing import Final


WORKFLOW_STATUS_PENDING: Final[str] = "pending"
WORKFLOW_STATUS_FETCHING: Final[str] = "fetching"
WORKFLOW_STATUS_GLOSSARY_REVIEW: Final[str] = "glossary_review"
WORKFLOW_STATUS_REJECTED: Final[str] = "rejected"
WORKFLOW_STATUS_TRANSLATING: Final[str] = "translating"
WORKFLOW_STATUS_EDITING: Final[str] = "editing"
WORKFLOW_STATUS_FINAL_REVIEW: Final[str] = "final_review"
WORKFLOW_STATUS_REVISE: Final[str] = "revise"
WORKFLOW_STATUS_SAVING: Final[str] = "saving"
WORKFLOW_STATUS_COMPLETE: Final[str] = "complete"
WORKFLOW_STATUS_ERROR: Final[str] = "error"

WORKFLOW_ERROR_STAGE_COMPLETE: Final[str] = "complete"
WORKFLOW_ERROR_CODE_SAVE_FAILED: Final[str] = "save_failed"
WORKFLOW_ERROR_CODE_SAVE_CONFLICT: Final[str] = "save_conflict"
