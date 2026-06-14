from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from novel_translation_backend.constants.workflow_status import (
    WORKFLOW_STATUS_ERROR,
    WORKFLOW_STATUS_FINAL_REVIEW,
    WORKFLOW_STATUS_GLOSSARY_REVIEW,
    WORKFLOW_STATUS_PENDING,
)
from novel_translation_backend.graph.runner import (
    WorkflowAlreadyRunningError,
    WorkflowNotFoundError,
    get_state,
    kill_workflow,
    start_graph,
)
from novel_translation_backend.graph.state import WorkflowState
from novel_translation_backend.llm.client import WORKFLOW_MODELS


router = APIRouter(prefix="/api/workflow", tags=["workflow"])


class StartWorkflowRequest(BaseModel):
    novel_name: str = Field(min_length=1)
    chapter_number: int = Field(gt=0, strict=True)


class StartWorkflowResponse(BaseModel):
    workflow_id: str


class WorkflowCommandResponse(BaseModel):
    ok: bool


class GlossaryTermResponse(BaseModel):
    term_key: str
    chinese: str
    proposed_english: str
    description: str
    approved_english: str | None
    status: str
    is_new: bool


class WorkflowStatusResponse(BaseModel):
    status: str
    error_detail: str | None
    glossary_terms: list[GlossaryTermResponse] | None
    edited_text: str | None


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

    try:
        await start_graph(workflow_id, initial_state)
    except WorkflowAlreadyRunningError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return StartWorkflowResponse(workflow_id=workflow_id)


@router.get("/{workflow_id}/status", response_model=WorkflowStatusResponse)
async def workflow_status(workflow_id: str) -> WorkflowStatusResponse:
    workflow_state = await get_state(workflow_id)
    if workflow_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        )

    workflow_status = workflow_state["status"]
    return WorkflowStatusResponse(
        status=workflow_status,
        error_detail=(
            workflow_state["error_detail"]
            if workflow_status == WORKFLOW_STATUS_ERROR
            else None
        ),
        glossary_terms=(
            [
                GlossaryTermResponse(term_key=term["chinese"], **term)
                for term in workflow_state["glossary_terms"]
                if term["is_new"]
            ]
            if workflow_status == WORKFLOW_STATUS_GLOSSARY_REVIEW
            else None
        ),
        edited_text=(
            workflow_state["edited_text"]
            if workflow_status == WORKFLOW_STATUS_FINAL_REVIEW
            else None
        ),
    )


@router.post("/{workflow_id}/kill", response_model=WorkflowCommandResponse)
async def kill_workflow_route(workflow_id: str) -> WorkflowCommandResponse:
    try:
        await kill_workflow(workflow_id)
    except WorkflowNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        ) from exc

    return WorkflowCommandResponse(ok=True)
