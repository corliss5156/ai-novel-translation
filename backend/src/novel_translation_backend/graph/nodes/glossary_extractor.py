from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from novel_translation_backend.constants.glossary_status import (
    GLOSSARY_STATUS_PENDING_REVIEW,
)
from novel_translation_backend.db.glossary_repo import get_approved_glossary_terms
from novel_translation_backend.graph.state import GlossaryTerm, WorkflowState
from novel_translation_backend.llm.client import NANO_MODEL, invoke


MAX_GLOSSARY_PROMPT_CHARACTERS = 20_000
APPROVED_GLOSSARY_MARKER = "{{APPROVED_GLOSSARY_JSON}}"
RAW_CHINESE_TEXT_MARKER = "{{RAW_CHINESE_TEXT}}"

def glossary_extractor_node(state: WorkflowState) -> WorkflowState:
    approved_terms = _deduplicate_approved_terms(
        get_approved_glossary_terms(state["novel_name"])
    )
    prompt = _build_prompt(state["raw_chinese_text"], approved_terms)

    proposed_terms = _parse_proposed_terms(invoke(prompt, model=NANO_MODEL))
    approved_chinese = {term["chinese"] for term in approved_terms}
    new_terms = [
        term for term in proposed_terms if term["chinese"] not in approved_chinese
    ]

    state["glossary_terms"] = [*approved_terms, *new_terms]
    return state


def _build_prompt(
    raw_chinese_text: str,
    approved_terms: list[GlossaryTerm],
) -> str:
    prompt_template = (
        files("novel_translation_backend.prompts")
        .joinpath("glossary_extractor.txt")
        .read_text(encoding="utf-8")
        .strip()
    )
    missing_markers = [
        marker
        for marker in (APPROVED_GLOSSARY_MARKER, RAW_CHINESE_TEXT_MARKER)
        if marker not in prompt_template
    ]
    if missing_markers:
        raise RuntimeError(
            "Glossary extractor prompt is missing required markers: "
            + ", ".join(missing_markers)
        )

    approved_payload = [
        {
            "chinese": term["chinese"],
            "approved_english": term["approved_english"],
        }
        for term in approved_terms
    ]
    prompt = prompt_template.replace(
        APPROVED_GLOSSARY_MARKER,
        json.dumps(approved_payload, ensure_ascii=False),
    ).replace(
        RAW_CHINESE_TEXT_MARKER,
        raw_chinese_text,
    )
    if len(prompt) > MAX_GLOSSARY_PROMPT_CHARACTERS:
        raise ValueError(
            "Glossary extractor prompt exceeds the "
            f"{MAX_GLOSSARY_PROMPT_CHARACTERS:,}-character limit "
            f"({len(prompt)} characters)."
        )
    return prompt


def _parse_proposed_terms(response: str) -> list[GlossaryTerm]:
    if not isinstance(response, str):
        raise ValueError("Glossary extractor response must be a JSON string")

    try:
        payload: Any = json.loads(response)
    except json.JSONDecodeError as exc:
        raise ValueError("Glossary extractor response must be valid JSON") from exc

    if not isinstance(payload, list):
        raise ValueError("Glossary extractor response must be a JSON array")

    terms_by_chinese: dict[str, GlossaryTerm] = {}
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(
                f"Glossary extractor item {index} must be a JSON object"
            )
        if set(item) != {"chinese", "proposed_english"}:
            raise ValueError(
                "Glossary extractor item "
                f"{index} must contain only chinese and proposed_english"
            )

        chinese = item["chinese"]
        proposed_english = item["proposed_english"]
        if not isinstance(chinese, str) or not chinese.strip():
            raise ValueError(
                f"Glossary extractor item {index} requires non-empty chinese"
            )
        if not isinstance(proposed_english, str) or not proposed_english.strip():
            raise ValueError(
                "Glossary extractor item "
                f"{index} requires non-empty proposed_english"
            )

        normalized_chinese = chinese.strip()
        if normalized_chinese not in terms_by_chinese:
            terms_by_chinese[normalized_chinese] = GlossaryTerm(
                chinese=normalized_chinese,
                proposed_english=proposed_english.strip(),
                approved_english=None,
                status=GLOSSARY_STATUS_PENDING_REVIEW,
                is_new=True,
            )

    return list(terms_by_chinese.values())


def _deduplicate_approved_terms(
    approved_terms: list[GlossaryTerm],
) -> list[GlossaryTerm]:
    terms_by_chinese: dict[str, GlossaryTerm] = {}
    for term in approved_terms:
        normalized_chinese = term["chinese"].strip()
        if normalized_chinese and normalized_chinese not in terms_by_chinese:
            terms_by_chinese[normalized_chinese] = GlossaryTerm(
                chinese=normalized_chinese,
                proposed_english=term["proposed_english"].strip(),
                approved_english=term["approved_english"],
                status=term["status"],
                is_new=False,
            )
    return list(terms_by_chinese.values())
