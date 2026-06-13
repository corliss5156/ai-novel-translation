from typing import List, Optional, TypedDict


class GlossaryTerm(TypedDict):
    chinese: str
    proposed_english: str
    approved_english: Optional[str]
    status: str
    is_new: bool


class WorkflowState(TypedDict):
    workflow_id: str
    novel_name: str
    chapter_number: int
    status: str
    raw_chinese_text: str
    glossary_terms: List[GlossaryTerm]
    translated_text: Optional[str]
    edited_text: Optional[str]
    final_text: Optional[str]
    editor_feedback: Optional[str]
    created_at: str
    completed_at: Optional[str]
    model_used: str
    error_detail: Optional[str]
