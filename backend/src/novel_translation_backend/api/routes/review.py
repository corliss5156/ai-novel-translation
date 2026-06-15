from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from novel_translation_backend.graph.runner import (
    InvalidEditorReviewFeedbackError,
    InvalidFinalReviewDecisionError,
    InvalidGlossaryDecisionsError,
    WorkflowNotFoundError,
    WorkflowNotPausedForFinalReviewError,
    WorkflowNotPausedForGlossaryReviewError,
    submit_editor_review,
    submit_final_review,
    submit_glossary_review,
)


router = APIRouter(prefix="/api/review", tags=["review"])


class GlossaryDecision(BaseModel):
    term_key: str = Field(min_length=1)
    action: Literal["approve", "reject"]
    approved_english: str | None = None

    @model_validator(mode="after")
    def validate_approved_english(self) -> "GlossaryDecision":
        if self.action == "approve" and (
            self.approved_english is None or not self.approved_english.strip()
        ):
            raise ValueError("approved_english is required when action is approve")
        return self


class GlossarySuggestion(BaseModel):
    chinese: str = Field(min_length=1)
    approved_english: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_values(self) -> "GlossarySuggestion":
        if not self.chinese.strip():
            raise ValueError("suggestion chinese must be non-empty")
        if not self.approved_english.strip():
            raise ValueError("suggestion approved_english must be non-empty")
        return self


class GlossaryReviewRequest(BaseModel):
    workflow_id: str = Field(min_length=1)
    decisions: list[GlossaryDecision]
    suggestions: list[GlossarySuggestion] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    ok: bool


class FinalReviewRequest(BaseModel):
    workflow_id: str = Field(min_length=1)
    final_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_final_text(self) -> "FinalReviewRequest":
        if not self.final_text.strip():
            raise ValueError("final_text must be non-empty")
        return self


class EditorReviewRequest(BaseModel):
    workflow_id: str = Field(min_length=1)
    feedback: str = Field(min_length=10)

    @model_validator(mode="after")
    def validate_feedback(self) -> "EditorReviewRequest":
        if len(self.feedback.strip()) < 10:
            raise ValueError("feedback must contain at least 10 characters")
        return self


@router.post("/glossary", response_model=ReviewResponse)
async def review_glossary(request: GlossaryReviewRequest) -> ReviewResponse:
    decisions_by_key: dict[str, tuple[str, str | None]] = {}
    for decision in request.decisions:
        term_key = decision.term_key.strip()
        if term_key in decisions_by_key:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Duplicate glossary term_key: {term_key}",
            )
        decisions_by_key[term_key] = (
            decision.action,
            (
                decision.approved_english.strip()
                if decision.approved_english is not None
                else None
            ),
        )

    suggestions_by_key: dict[str, str] = {}
    for suggestion in request.suggestions:
        term_key = suggestion.chinese.strip()
        if term_key in suggestions_by_key:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Duplicate glossary suggestion: {term_key}",
            )
        suggestions_by_key[term_key] = suggestion.approved_english.strip()

    try:
        await submit_glossary_review(
            request.workflow_id,
            decisions_by_key,
            suggestions_by_key,
        )
    except WorkflowNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        ) from exc
    except WorkflowNotPausedForGlossaryReviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow is not paused for glossary review",
        ) from exc
    except InvalidGlossaryDecisionsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return ReviewResponse(ok=True)


@router.post("/final", response_model=ReviewResponse)
async def review_final(request: FinalReviewRequest) -> ReviewResponse:
    try:
        await submit_final_review(request.workflow_id, request.final_text)
    except WorkflowNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        ) from exc
    except WorkflowNotPausedForFinalReviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow is not paused for final review",
        ) from exc
    except InvalidFinalReviewDecisionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return ReviewResponse(ok=True)


@router.post("/editor", response_model=ReviewResponse)
async def review_editor(request: EditorReviewRequest) -> ReviewResponse:
    try:
        await submit_editor_review(request.workflow_id, request.feedback)
    except WorkflowNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        ) from exc
    except WorkflowNotPausedForFinalReviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow is not paused for final review",
        ) from exc
    except InvalidEditorReviewFeedbackError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return ReviewResponse(ok=True)
