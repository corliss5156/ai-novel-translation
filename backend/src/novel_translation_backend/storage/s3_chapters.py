from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.exceptions import ClientError


RAW_PREFIX = "raw"
TRANSLATED_PREFIX = "translated"
DEFAULT_BUCKET_NAME = "novel-translation"


class ChapterNotFoundError(FileNotFoundError):
    """Raised when a requested raw chapter object does not exist in S3."""


class ChapterAlreadyExistsError(FileExistsError):
    """Raised when a translated chapter object already exists in S3."""


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


def fetch_chapter(novel_name: str, chapter_number: int) -> str:
    """Fetch raw Chinese chapter text from S3."""
    bucket = _bucket_name()
    key = _chapter_key(RAW_PREFIX, novel_name, chapter_number)

    try:
        response = _s3_client().get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404", "NotFound"}:
            raise ChapterNotFoundError(
                f"Chapter not found at s3://{bucket}/{key}"
            ) from exc
        raise

    content = response["Body"].read().decode("utf-8")
    if not content.strip():
        raise ChapterNotFoundError(f"Chapter at s3://{bucket}/{key} is empty")
    return content


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
