from contextlib import AbstractContextManager
import json
from types import TracebackType
from typing import Any

from novel_translation_backend.constants.glossary_status import (
    GLOSSARY_STATUS_APPROVED,
)
from novel_translation_backend.db import glossary_repo
from novel_translation_backend.graph.state import GlossaryTerm


class RecordingTransaction(AbstractContextManager["RecordingSession"]):
    def __init__(self, session: "RecordingSession") -> None:
        self.session = session

    def __enter__(self) -> "RecordingSession":
        return self.session

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class RecordingSession:
    def __init__(self) -> None:
        self.statement: Any = None
        self.parameters: dict[str, Any] | None = None

    def execute(self, statement: Any, parameters: dict[str, Any]) -> None:
        self.statement = statement
        self.parameters = parameters


class RecordingSessionFactory:
    def __init__(self, session: RecordingSession) -> None:
        self.session = session

    def begin(self) -> RecordingTransaction:
        return RecordingTransaction(self.session)


def test_apply_glossary_decisions_explicitly_types_reused_novel_name(
    monkeypatch: Any,
) -> None:
    session = RecordingSession()
    monkeypatch.setattr(
        glossary_repo,
        "get_session_factory",
        lambda: RecordingSessionFactory(session),
    )
    approved_term = GlossaryTerm(
        chinese="神光宗",
        proposed_english="Divine Radiance Sect",
        description="A prominent cultivation sect.",
        approved_english="Divine Radiance Sect",
        status=GLOSSARY_STATUS_APPROVED,
        is_new=True,
    )

    glossary_repo.apply_glossary_decisions("test-novel", 1, [approved_term])

    assert str(session.statement).count("CAST(:novel_name AS text)") == 2
    assert session.parameters is not None
    assert json.loads(session.parameters["term_payload"]) == [
        {
            "chinese": "神光宗",
            "english": "Divine Radiance Sect",
            "description": "A prominent cultivation sect.",
        }
    ]
