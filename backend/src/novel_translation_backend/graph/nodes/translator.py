from __future__ import annotations

import json
from importlib.resources import files

from novel_translation_backend.constants.glossary_status import (
    GLOSSARY_STATUS_APPROVED,
)
from novel_translation_backend.constants.workflow_status import (
    WORKFLOW_STATUS_TRANSLATING,
)
from novel_translation_backend.graph.state import GlossaryTerm, WorkflowState
from novel_translation_backend.llm.client import MINI_MODEL, invoke


MAX_TRANSLATOR_PROMPT_CHARACTERS = 20_000
APPROVED_GLOSSARY_MARKER = "{{APPROVED_GLOSSARY_JSON}}"
RAW_CHINESE_TEXT_MARKER = "{{RAW_CHINESE_TEXT}}"

def translator_node(state: WorkflowState) -> WorkflowState:
    state["status"] = WORKFLOW_STATUS_TRANSLATING

    raw_chinese_text = state["raw_chinese_text"]
    approved_terms = _approved_terms(state["glossary_terms"])
    prompt = _build_prompt(raw_chinese_text, approved_terms)

    translated_text = _validate_translation(invoke(prompt, model=MINI_MODEL))
    state["translated_text"] = translated_text
    existing_warnings = state["warnings"]
    state["warnings"] = list(
        dict.fromkeys(
            [
                *existing_warnings,
                *_missing_glossary_warnings(
                    raw_chinese_text,
                    translated_text,
                    approved_terms,
                ),
            ]
        )
    )
    return state


def _approved_terms(glossary_terms: list[GlossaryTerm]) -> list[GlossaryTerm]:
    approved_terms: list[GlossaryTerm] = []
    for term in glossary_terms:
        if term["status"] != GLOSSARY_STATUS_APPROVED:
            continue
        approved_english = term["approved_english"]
        if approved_english is None or not approved_english.strip():
            raise ValueError(
                "Approved glossary term requires approved English: "
                f"{term['chinese']}"
            )
        approved_terms.append(term)
    return approved_terms


def _build_prompt(
    raw_chinese_text: str,
    approved_terms: list[GlossaryTerm],
) -> str:
    prompt_template = (
        files("novel_translation_backend.prompts")
        .joinpath("translator.txt")
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
            "Translator prompt is missing required markers: "
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
    if len(prompt) > MAX_TRANSLATOR_PROMPT_CHARACTERS:
        raise ValueError(
            "Translator prompt exceeds the "
            f"{MAX_TRANSLATOR_PROMPT_CHARACTERS:,}-character limit "
            f"({len(prompt)} characters)."
        )
    return prompt


def _validate_translation(response: str) -> str:
    if not isinstance(response, str):
        raise ValueError("Translator response must be a string")
    translated_text = response.strip()
    if not translated_text:
        raise ValueError("Translator response must be a non-empty string")
    return translated_text


def _missing_glossary_warnings(
    raw_chinese_text: str,
    translated_text: str,
    approved_terms: list[GlossaryTerm],
) -> list[str]:
    warnings: list[str] = []
    warned_terms: set[tuple[str, str]] = set()
    for term in approved_terms:
        chinese = term["chinese"].strip()
        approved_english = term["approved_english"]
        if approved_english is None:
            continue
        english = approved_english.strip()
        term_pair = (chinese, english)
        if (
            chinese
            and chinese in raw_chinese_text
            and english not in translated_text
            and term_pair not in warned_terms
        ):
            warnings.append(
                "Translation may be missing approved glossary term "
                f"'{chinese}' as '{english}'."
            )
            warned_terms.add(term_pair)
    return warnings
