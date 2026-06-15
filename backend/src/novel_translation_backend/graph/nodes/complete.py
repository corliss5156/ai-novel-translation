from datetime import datetime, timezone

from novel_translation_backend.constants.workflow_status import (
    WORKFLOW_STATUS_COMPLETE,
    WORKFLOW_STATUS_SAVING,
)
from novel_translation_backend.graph.state import WorkflowState
from novel_translation_backend.storage.s3_chapters import save_final_chapter


def complete_node(state: WorkflowState) -> WorkflowState:
    final_text = state["final_text"]
    if final_text is None or not final_text.strip():
        raise ValueError("final_text must be non-empty before workflow completion")

    state["status"] = WORKFLOW_STATUS_SAVING
    save_final_chapter(
        novel_name=state["novel_name"],
        chapter_number=state["chapter_number"],
        final_text=final_text,
    )
    state["completed_at"] = datetime.now(timezone.utc).isoformat()
    state["status"] = WORKFLOW_STATUS_COMPLETE
    state["error_detail"] = None
    state["error_stage"] = None
    state["error_code"] = None
    return state
