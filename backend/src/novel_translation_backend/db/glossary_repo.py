from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import text

from novel_translation_backend.constants.glossary_status import (
    GLOSSARY_STATUS_APPROVED,
)
from novel_translation_backend.db.session import get_session_factory
from novel_translation_backend.graph.state import GlossaryTerm


def apply_glossary_decisions(
    novel_name: str,
    chapter_number: int,
    approved_terms: Sequence[GlossaryTerm],
) -> None:
    """Insert newly approved terms in one transaction and one database call."""
    if not approved_terms:
        return

    terms_by_chinese = {
        term["chinese"]: term["approved_english"] for term in approved_terms
    }
    term_payload = [
        {"chinese": chinese, "english": english}
        for chinese, english in terms_by_chinese.items()
    ]

    statement = text(
        """
        INSERT INTO glossary (
            novel_name,
            chinese,
            english,
            description,
            translated_at_chapter,
            status
        )
        SELECT
            :novel_name,
            decision.chinese,
            decision.english,
            '',
            :chapter_number,
            :approved_status
        FROM jsonb_to_recordset(CAST(:term_payload AS jsonb))
            AS decision(chinese text, english text)
        WHERE decision.english IS NOT NULL
          AND BTRIM(decision.english) <> ''
          AND NOT EXISTS (
              SELECT 1
              FROM glossary existing
              WHERE existing.novel_name = :novel_name
                AND existing.chinese = decision.chinese
          )
        """
    )

    with get_session_factory().begin() as session:
        session.execute(
            statement,
            {
                "novel_name": novel_name,
                "chapter_number": chapter_number,
                "approved_status": GLOSSARY_STATUS_APPROVED,
                "term_payload": json.dumps(term_payload),
            },
        )
