from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from novel_translation_backend.constants.workflow_status import WORKFLOW_STATUS_PENDING
from novel_translation_backend.graph.runner import get_state, start_graph
from novel_translation_backend.graph.state import WorkflowState
from novel_translation_backend.llm.client import WORKFLOW_MODELS


router = APIRouter(prefix="/api/workflow", tags=["workflow"])


class StartWorkflowRequest(BaseModel):
    novel_name: str = Field(min_length=1)
    chapter_number: int = Field(gt=0)


class StartWorkflowResponse(BaseModel):
    workflow_id: str


@router.post("/start", response_model=StartWorkflowResponse)
async def start_workflow(request: StartWorkflowRequest) -> StartWorkflowResponse:
    workflow_id = str(uuid4())
    initial_state = WorkflowState(
        workflow_id=workflow_id,
        novel_name=request.novel_name,
        chapter_number=request.chapter_number,
        status=WORKFLOW_STATUS_PENDING,
        raw_chinese_text="",
        glossary_terms=[],
        translated_text=None,
        edited_text=None,
        final_text=None,
        editor_feedback=None,
        created_at=datetime.now(timezone.utc).isoformat(),
        completed_at=None,
        model_used=WORKFLOW_MODELS,
        error_detail=None,
        warnings=[],
    )

    await start_graph(workflow_id, initial_state)
    return StartWorkflowResponse(workflow_id=workflow_id)


@router.get("/{workflow_id}/status", response_model=None)
async def workflow_status(workflow_id: str) -> WorkflowState:
    workflow_state = await get_state(workflow_id)
    if workflow_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        )

    return workflow_state
