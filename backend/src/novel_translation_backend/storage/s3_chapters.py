from __future__ import annotations

import os
import re
from typing import Any, TypedDict, cast

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]


RAW_PREFIX = "raw"
TRANSLATED_PREFIX = "translated"
DEFAULT_BUCKET_NAME = "novel-translation"
CHAPTER_KEY_PATTERN = re.compile(
    r"^(?P<prefix>raw|translated)/(?P<novel_name>[^/]+)/chapter-(?P<chapter_number>\d{3,})\.txt$"
)


class ChapterCatalogItem(TypedDict):
    chapter_number: int
    translated: bool


class ChapterNotFoundError(FileNotFoundError):
    """Raised when a requested chapter object does not exist in S3."""


class ChapterAlreadyExistsError(FileExistsError):
    """Raised when a translated chapter object already exists in S3."""


class ChapterSaveError(RuntimeError):
    """Raised when an approved chapter cannot be saved to S3."""


class ChapterSaveConflictError(ChapterSaveError):
    """Raised when a different translated chapter already exists in S3."""


def _bucket_name() -> str:
    return os.getenv("S3_BUCKET_NAME", DEFAULT_BUCKET_NAME)


def _s3_client() -> Any:
    region_name = os.getenv("AWS_REGION")
    if region_name:
        return boto3.client("s3", region_name=region_name)
    return boto3.client("s3")


def _chapter_key(prefix: str, novel_name: str, chapter_number: int) -> str:
    if not novel_name.strip():
        raise ValueError("novel_name must be a non-empty string")
    if chapter_number < 1:
        raise ValueError("chapter_number must be greater than zero")

    return f"{prefix}/{novel_name}/chapter-{chapter_number:04d}.txt"


def _fetch_chapter(prefix: str, novel_name: str, chapter_number: int) -> str:
    bucket = _bucket_name()
    key = _chapter_key(prefix, novel_name, chapter_number)

    try:
        response = _s3_client().get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404", "NotFound"}:
            raise ChapterNotFoundError(
                f"Chapter not found at s3://{bucket}/{key}"
            ) from exc
        raise

    content = cast(bytes, response["Body"].read()).decode("utf-8")
    if not content.strip():
        raise ChapterNotFoundError(f"Chapter at s3://{bucket}/{key} is empty")
    return content


def fetch_chapter(novel_name: str, chapter_number: int) -> str:
    """Fetch raw Chinese chapter text from S3."""
    return _fetch_chapter(RAW_PREFIX, novel_name, chapter_number)


def fetch_translated_chapter(novel_name: str, chapter_number: int) -> str:
    """Fetch translated English chapter text from S3."""
    return _fetch_chapter(TRANSLATED_PREFIX, novel_name, chapter_number)


def _list_keys(prefix: str) -> list[str]:
    client = _s3_client()
    bucket = _bucket_name()
    keys: list[str] = []
    continuation_token: str | None = None

    while True:
        parameters: dict[str, Any] = {
            "Bucket": bucket,
            "Prefix": f"{prefix}/",
        }
        if continuation_token is not None:
            parameters["ContinuationToken"] = continuation_token

        response = client.list_objects_v2(**parameters)
        keys.extend(
            item["Key"]
            for item in response.get("Contents", [])
            if isinstance(item.get("Key"), str)
        )

        if not response.get("IsTruncated"):
            return keys
        continuation_token = response["NextContinuationToken"]


def _parse_chapter_key(key: str, prefix: str) -> tuple[str, int] | None:
    match = CHAPTER_KEY_PATTERN.fullmatch(key)
    if match is None or match.group("prefix") != prefix:
        return None
    chapter_number = int(match.group("chapter_number"))
    if chapter_number < 1:
        return None
    return match.group("novel_name"), chapter_number


def list_chapters() -> dict[str, list[ChapterCatalogItem]]:
    """List raw chapters grouped by novel with translated status."""
    raw_chapters = {
        parsed
        for key in _list_keys(RAW_PREFIX)
        if (parsed := _parse_chapter_key(key, RAW_PREFIX)) is not None
    }
    translated_chapters = {
        parsed
        for key in _list_keys(TRANSLATED_PREFIX)
        if (parsed := _parse_chapter_key(key, TRANSLATED_PREFIX)) is not None
    }

    catalog: dict[str, list[ChapterCatalogItem]] = {}
    for novel_name, chapter_number in sorted(raw_chapters):
        catalog.setdefault(novel_name, []).append(
            {
                "chapter_number": chapter_number,
                "translated": (novel_name, chapter_number)
                in translated_chapters,
            }
        )
    return catalog


def upload_chapter(novel_name: str, chapter_number: int, content: str) -> None:
    """Create a translated chapter without overwriting an existing object."""
    bucket = _bucket_name()
    key = _chapter_key(TRANSLATED_PREFIX, novel_name, chapter_number)

    try:
        _s3_client().put_object(
            Bucket=bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
            IfNoneMatch="*",
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        status_code = exc.response.get("ResponseMetadata", {}).get(
            "HTTPStatusCode"
        )
        if error_code in {"PreconditionFailed", "412"} or status_code == 412:
            raise ChapterAlreadyExistsError(
                f"Translated chapter already exists at s3://{bucket}/{key}"
            ) from exc
        raise


def save_final_chapter(
    novel_name: str,
    chapter_number: int,
    final_text: str,
) -> None:
    """Save approved text once, treating an identical existing object as success."""
    if not final_text.strip():
        raise ValueError("final_text must be a non-empty string")

    try:
        upload_chapter(novel_name, chapter_number, final_text)
        return
    except ChapterAlreadyExistsError:
        pass
    except Exception as exc:
        raise ChapterSaveError("Unable to save the approved translation") from exc

    try:
        existing_text = fetch_translated_chapter(novel_name, chapter_number)
    except Exception as exc:
        raise ChapterSaveError(
            "Unable to verify the existing translated chapter"
        ) from exc

    if existing_text == final_text:
        return

    raise ChapterSaveConflictError(
        "A different translated chapter already exists and will not be overwritten"
    )
