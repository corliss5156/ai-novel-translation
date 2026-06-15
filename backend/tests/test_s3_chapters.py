from typing import Any

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from novel_translation_backend.storage import s3_chapters


class RecordingS3Client:
    def __init__(self) -> None:
        self.put_parameters: dict[str, Any] | None = None

    def put_object(self, **parameters: Any) -> None:
        self.put_parameters = parameters


class Body:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def read(self) -> bytes:
        return self.content


class CatalogS3Client:
    def __init__(self) -> None:
        self.list_parameters: list[dict[str, Any]] = []

    def list_objects_v2(self, **parameters: Any) -> dict[str, Any]:
        self.list_parameters.append(parameters)
        prefix = parameters["Prefix"]
        token = parameters.get("ContinuationToken")

        if prefix == "raw/" and token is None:
            return {
                "Contents": [
                    {"Key": "raw/beta/chapter-0010.txt"},
                    {"Key": "raw/alpha/chapter-0002.txt"},
                    {"Key": "raw/alpha/notes.txt"},
                ],
                "IsTruncated": True,
                "NextContinuationToken": "raw-page-2",
            }
        if prefix == "raw/" and token == "raw-page-2":
            return {
                "Contents": [
                    {"Key": "raw/alpha/chapter-0001.txt"},
                    {"Key": "raw/alpha/chapter-0002.txt"},
                ],
                "IsTruncated": False,
            }
        return {
            "Contents": [
                {"Key": "translated/alpha/chapter-002.txt"},
                {"Key": "translated/orphan/chapter-0001.txt"},
            ],
            "IsTruncated": False,
        }


def test_upload_chapter_creates_plain_text_file(monkeypatch: Any) -> None:
    client = RecordingS3Client()
    monkeypatch.setattr(s3_chapters, "_s3_client", lambda: client)
    monkeypatch.setattr(s3_chapters, "_bucket_name", lambda: "test-bucket")

    s3_chapters.upload_chapter("test-novel", 12, "Translated chapter")

    assert client.put_parameters == {
        "Bucket": "test-bucket",
        "Key": "translated/test-novel/chapter-0012.txt",
        "Body": b"Translated chapter",
        "ContentType": "text/plain; charset=utf-8",
        "IfNoneMatch": "*",
    }


def test_list_chapters_returns_sorted_raw_catalog_with_translated_status(
    monkeypatch: Any,
) -> None:
    client = CatalogS3Client()
    monkeypatch.setattr(s3_chapters, "_s3_client", lambda: client)
    monkeypatch.setattr(s3_chapters, "_bucket_name", lambda: "test-bucket")

    catalog = s3_chapters.list_chapters()

    assert catalog == {
        "alpha": [
            {"chapter_number": 1, "translated": False},
            {"chapter_number": 2, "translated": True},
        ],
        "beta": [{"chapter_number": 10, "translated": False}],
    }
    assert client.list_parameters[1]["ContinuationToken"] == "raw-page-2"


def test_list_chapters_returns_empty_catalog_when_no_raw_chapters(
    monkeypatch: Any,
) -> None:
    class EmptyS3Client:
        def list_objects_v2(self, **parameters: Any) -> dict[str, Any]:
            return {"IsTruncated": False}

    monkeypatch.setattr(s3_chapters, "_s3_client", lambda: EmptyS3Client())

    assert s3_chapters.list_chapters() == {}


def test_fetch_translated_chapter_reads_translated_object(monkeypatch: Any) -> None:
    class FetchS3Client:
        def get_object(self, **parameters: Any) -> dict[str, Any]:
            assert parameters["Key"] == "translated/test-novel/chapter-0012.txt"
            return {"Body": Body(b"Translated chapter")}

    monkeypatch.setattr(s3_chapters, "_s3_client", lambda: FetchS3Client())
    monkeypatch.setattr(s3_chapters, "_bucket_name", lambda: "test-bucket")

    assert (
        s3_chapters.fetch_translated_chapter("test-novel", 12)
        == "Translated chapter"
    )


def test_fetch_translated_chapter_raises_when_object_is_missing(
    monkeypatch: Any,
) -> None:
    class MissingS3Client:
        def get_object(self, **parameters: Any) -> dict[str, Any]:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey"}},
                "GetObject",
            )

    monkeypatch.setattr(s3_chapters, "_s3_client", lambda: MissingS3Client())

    with pytest.raises(s3_chapters.ChapterNotFoundError):
        s3_chapters.fetch_translated_chapter("test-novel", 12)
