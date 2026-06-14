from typing import Any

from novel_translation_backend.storage import s3_chapters


class RecordingS3Client:
    def __init__(self) -> None:
        self.put_parameters: dict[str, Any] | None = None

    def put_object(self, **parameters: Any) -> None:
        self.put_parameters = parameters


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
