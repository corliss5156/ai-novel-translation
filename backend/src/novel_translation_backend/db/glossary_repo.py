from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import bindparam, text

from novel_translation_backend.constants.glossary_status import (
    GLOSSARY_STATUS_APPROVED,
)
from novel_translation_backend.db.session import get_session_factory
from novel_translation_backend.graph.state import GlossaryTerm


def get_approved_glossary_terms(
    novel_name: str,
    chinese_terms: Sequence[str],
) -> list[GlossaryTerm]:
    """Load exact approved matches for extracted terms from one novel."""
    normalized_terms = list(
        dict.fromkeys(term.strip() for term in chinese_terms if term.strip())
    )
    if not normalized_terms:
        return []

    statement = text(
        """
        SELECT chinese, english, description
        FROM glossary
        WHERE novel_name = :novel_name
          AND status = :approved_status
          AND BTRIM(chinese) IN :chinese_terms
        ORDER BY created_at, id
        """
    ).bindparams(bindparam("chinese_terms", expanding=True))

    with get_session_factory()() as session:
        rows = session.execute(
            statement,
            {
                "novel_name": novel_name,
                "approved_status": GLOSSARY_STATUS_APPROVED,
                "chinese_terms": normalized_terms,
            },
        ).mappings()

        return [
            GlossaryTerm(
                chinese=row["chinese"].strip(),
                proposed_english=row["english"],
                description=row["description"],
                approved_english=row["english"],
                status=GLOSSARY_STATUS_APPROVED,
                is_new=False,
            )
            for row in rows
        ]


def apply_glossary_decisions(
    novel_name: str,
    chapter_number: int,
    approved_terms: Sequence[GlossaryTerm],
) -> None:
    """Insert newly approved terms in one transaction and one database call."""
    if not approved_terms:
        return

    terms_by_chinese = {term["chinese"]: term for term in approved_terms}
    term_payload = [
        {
            "chinese": chinese,
            "english": term["approved_english"],
            "description": term["description"],
        }
        for chinese, term in terms_by_chinese.items()
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
            CAST(:novel_name AS text),
            decision.chinese,
            decision.english,
            decision.description,
            :chapter_number,
            :approved_status
        FROM jsonb_to_recordset(CAST(:term_payload AS jsonb))
            AS decision(chinese text, english text, description text)
        WHERE decision.english IS NOT NULL
          AND BTRIM(decision.english) <> ''
          AND NOT EXISTS (
              SELECT 1
              FROM glossary existing
              WHERE existing.novel_name = CAST(:novel_name AS text)
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
