from novel_translation_backend.constants.glossary_status import (
    GLOSSARY_STATUS_APPROVED,
)
from novel_translation_backend.db.glossary_repo import apply_glossary_decisions
from novel_translation_backend.graph.state import WorkflowState


def glossary_db_write_node(state: WorkflowState) -> WorkflowState:
    approved_terms = [
        term
        for term in state["glossary_terms"]
        if term["status"] == GLOSSARY_STATUS_APPROVED
    ]
    invalid_approved_terms = [
        term["chinese"]
        for term in approved_terms
        if term["approved_english"] is None
        or not term["approved_english"].strip()
    ]
    if invalid_approved_terms:
        invalid_terms = ", ".join(invalid_approved_terms)
        raise ValueError(
            f"Approved glossary terms require approved English values: {invalid_terms}"
        )

    newly_approved_terms = [term for term in approved_terms if term["is_new"]]

    apply_glossary_decisions(
        novel_name=state["novel_name"],
        chapter_number=state["chapter_number"],
        approved_terms=newly_approved_terms,
    )
    state["glossary_terms"] = approved_terms
    return state
