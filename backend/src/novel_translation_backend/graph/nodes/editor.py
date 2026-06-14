from __future__ import annotations

import json
from importlib.resources import files

from novel_translation_backend.constants.workflow_status import WORKFLOW_STATUS_EDITING
from novel_translation_backend.graph.state import WorkflowState
from novel_translation_backend.llm.client import NANO_MODEL, invoke


MAX_EDITOR_PROMPT_CHARACTERS = 20_000
MAX_EDITOR_CORRECTION_RETRIES = 2

TRANSLATED_TEXT_MARKER = "{{TRANSLATED_TEXT}}"
EDITOR_FEEDBACK_MARKER = "{{EDITOR_FEEDBACK}}"
INVALID_EDITED_TEXT_MARKER = "{{INVALID_EDITED_TEXT}}"
VALIDATION_FAILURES_MARKER = "{{VALIDATION_FAILURES}}"

def editor_node(state: WorkflowState) -> WorkflowState:
    state["status"] = WORKFLOW_STATUS_EDITING

    translated_text = state["translated_text"]
    if translated_text is None or not translated_text.strip():
        raise ValueError("translated_text must be non-empty before editing")
    invalid_edited_text: str | None = None
    validation_failures: list[str] = []
    for attempt in range(MAX_EDITOR_CORRECTION_RETRIES + 1):
        prompt = _build_prompt(
            translated_text=translated_text,
            editor_feedback=state["editor_feedback"],
            invalid_edited_text=invalid_edited_text,
            validation_failures=validation_failures,
        )
        edited_text = _validate_non_empty_response(invoke(prompt, model=NANO_MODEL))
        validation_failures = _formatting_failures(edited_text)
        if not validation_failures:
            state["edited_text"] = edited_text
            return state
        invalid_edited_text = edited_text

    failures = "; ".join(validation_failures)
    raise ValueError(
        "Editor response failed formatting validation after "
        f"{MAX_EDITOR_CORRECTION_RETRIES + 1} attempts: {failures}"
    )


def _build_prompt(
    translated_text: str,
    editor_feedback: str | None,
    invalid_edited_text: str | None,
    validation_failures: list[str],
) -> str:
    prompt_template = (
        files("novel_translation_backend.prompts")
        .joinpath("editor.txt")
        .read_text(encoding="utf-8")
        .strip()
    )
    replacements = {
        TRANSLATED_TEXT_MARKER: translated_text,
        EDITOR_FEEDBACK_MARKER: json.dumps(editor_feedback, ensure_ascii=False),
        INVALID_EDITED_TEXT_MARKER: json.dumps(
            invalid_edited_text,
            ensure_ascii=False,
        ),
        VALIDATION_FAILURES_MARKER: json.dumps(
            validation_failures,
            ensure_ascii=False,
        ),
    }
    missing_markers = [
        marker for marker in replacements if marker not in prompt_template
    ]
    if missing_markers:
        raise RuntimeError(
            "Editor prompt is missing required markers: "
            + ", ".join(missing_markers)
        )

    prompt = prompt_template
    for marker, value in replacements.items():
        prompt = prompt.replace(marker, value)

    if len(prompt) > MAX_EDITOR_PROMPT_CHARACTERS:
        raise ValueError(
            "Editor prompt exceeds the "
            f"{MAX_EDITOR_PROMPT_CHARACTERS:,}-character limit "
            f"({len(prompt)} characters)."
        )
    return prompt


def _validate_non_empty_response(response: str) -> str:
    if not isinstance(response, str):
        raise ValueError("Editor response must be a string")
    edited_text = response.strip()
    if not edited_text:
        raise ValueError("Editor response must be a non-empty string")
    return edited_text


def _formatting_failures(edited_text: str) -> list[str]:
    failures: list[str] = []
    if "-" in edited_text:
        failures.append("Editor response contains a hyphen")
    if "—" in edited_text:
        failures.append("Editor response contains an em dash")
    return failures
