from novel_translation_backend.constants.workflow_status import (
    WORKFLOW_STATUS_FETCHING,
)
from novel_translation_backend.graph.state import WorkflowState
from novel_translation_backend.storage.s3_chapters import (
    ChapterNotFoundError,
    fetch_chapter,
)


def s3_retrieval_node(state: WorkflowState) -> WorkflowState:
    state["status"] = WORKFLOW_STATUS_FETCHING

    raw_chinese_text = fetch_chapter(
        novel_name=state["novel_name"],
        chapter_number=state["chapter_number"],
    )
    if not raw_chinese_text.strip():
        raise ChapterNotFoundError(
            "Fetched chapter content is empty for "
            f"{state['novel_name']} chapter {state['chapter_number']}"
        )

    state["raw_chinese_text"] = raw_chinese_text
    return state
