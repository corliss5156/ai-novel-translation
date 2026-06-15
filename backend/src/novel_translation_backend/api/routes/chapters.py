from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel

from novel_translation_backend.storage.s3_chapters import (
    ChapterNotFoundError,
    fetch_chapter,
    fetch_translated_chapter,
    list_chapters,
)


router = APIRouter(prefix="/api/chapters", tags=["chapters"])


class ChapterCatalogEntry(BaseModel):
    chapter_number: int
    translated: bool


class NovelCatalogEntry(BaseModel):
    novel_name: str
    chapters: list[ChapterCatalogEntry]


class ChapterCatalogResponse(BaseModel):
    novels: list[NovelCatalogEntry]


class ChapterResponse(BaseModel):
    novel_name: str
    chapter_number: int
    raw_chinese_text: str
    translated_text: str


@router.get("", response_model=ChapterCatalogResponse)
async def chapter_catalog() -> ChapterCatalogResponse:
    catalog = list_chapters()
    return ChapterCatalogResponse(
        novels=[
            NovelCatalogEntry(
                novel_name=novel_name,
                chapters=[
                    ChapterCatalogEntry(
                        chapter_number=chapter_entry["chapter_number"],
                        translated=chapter_entry["translated"],
                    )
                    for chapter_entry in chapter_entries
                ],
            )
            for novel_name, chapter_entries in catalog.items()
        ]
    )


@router.get("/{novel_name}/{chapter_number}", response_model=ChapterResponse)
async def chapter(
    novel_name: str,
    chapter_number: int = Path(gt=0),
) -> ChapterResponse:
    try:
        raw_chinese_text = fetch_chapter(novel_name, chapter_number)
        translated_text = fetch_translated_chapter(novel_name, chapter_number)
    except ChapterNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return ChapterResponse(
        novel_name=novel_name,
        chapter_number=chapter_number,
        raw_chinese_text=raw_chinese_text,
        translated_text=translated_text,
    )
