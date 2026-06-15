from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novel_translation_backend.api.routes import chapters
from novel_translation_backend.storage.s3_chapters import ChapterNotFoundError


def create_client() -> TestClient:
    app = FastAPI()
    app.include_router(chapters.router)
    return TestClient(app)


def test_catalog_returns_novels_and_chapters(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        chapters,
        "list_chapters",
        lambda: {
            "alpha": [
                {"chapter_number": 1, "translated": False},
                {"chapter_number": 2, "translated": True},
            ]
        },
    )

    response = create_client().get("/api/chapters")

    assert response.status_code == 200
    assert response.json() == {
        "novels": [
            {
                "novel_name": "alpha",
                "chapters": [
                    {"chapter_number": 1, "translated": False},
                    {"chapter_number": 2, "translated": True},
                ],
            }
        ]
    }


def test_catalog_returns_empty_novels_list(monkeypatch: Any) -> None:
    monkeypatch.setattr(chapters, "list_chapters", lambda: {})

    response = create_client().get("/api/chapters")

    assert response.status_code == 200
    assert response.json() == {"novels": []}


def test_chapter_returns_raw_and_translated_plain_text(monkeypatch: Any) -> None:
    monkeypatch.setattr(chapters, "fetch_chapter", lambda novel, number: "原文")
    monkeypatch.setattr(
        chapters,
        "fetch_translated_chapter",
        lambda novel, number: "Translation",
    )

    response = create_client().get("/api/chapters/test-novel/3")

    assert response.status_code == 200
    assert response.json() == {
        "novel_name": "test-novel",
        "chapter_number": 3,
        "raw_chinese_text": "原文",
        "translated_text": "Translation",
    }


def test_chapter_returns_404_when_raw_chapter_is_missing(monkeypatch: Any) -> None:
    def missing_raw(novel_name: str, chapter_number: int) -> str:
        raise ChapterNotFoundError("Raw chapter not found")

    monkeypatch.setattr(chapters, "fetch_chapter", missing_raw)

    response = create_client().get("/api/chapters/test-novel/3")

    assert response.status_code == 404
    assert response.json() == {"detail": "Raw chapter not found"}


def test_chapter_returns_404_when_translation_is_missing(monkeypatch: Any) -> None:
    def missing_translation(novel_name: str, chapter_number: int) -> str:
        raise ChapterNotFoundError("Translated chapter not found")

    monkeypatch.setattr(chapters, "fetch_chapter", lambda novel, number: "原文")
    monkeypatch.setattr(
        chapters,
        "fetch_translated_chapter",
        missing_translation,
    )

    response = create_client().get("/api/chapters/test-novel/3")

    assert response.status_code == 404
    assert response.json() == {"detail": "Translated chapter not found"}


def test_chapter_rejects_non_positive_chapter_number() -> None:
    response = create_client().get("/api/chapters/test-novel/0")

    assert response.status_code == 422
