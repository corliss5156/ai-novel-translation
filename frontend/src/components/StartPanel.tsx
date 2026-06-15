"use client";

import { useEffect, useMemo, useState } from "react";

import styles from "./StartPanel.module.css";

export type ChapterSelection = {
  novelName: string;
  chapterNumber: number;
};

type ChapterEntry = {
  chapter_number: number;
  translated: boolean;
};

type NovelEntry = {
  novel_name: string;
  chapters: ChapterEntry[];
};

type CatalogResponse = {
  novels: NovelEntry[];
};

type StartPanelProps = {
  onOpenChapter: (selection: ChapterSelection) => void;
  onWorkflowStarted: (
    workflowId: string,
    selection: ChapterSelection,
  ) => void;
  preferredAfterSelection?: ChapterSelection | null;
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function responseError(response: Response, fallback: string) {
  try {
    const body = (await response.json()) as { detail?: string; error?: string };
    return body.detail ?? body.error ?? fallback;
  } catch {
    return fallback;
  }
}

export default function StartPanel({
  onOpenChapter,
  onWorkflowStarted,
  preferredAfterSelection,
}: StartPanelProps) {
  const [novels, setNovels] = useState<NovelEntry[]>([]);
  const [novelName, setNovelName] = useState("");
  const [chapterNumber, setChapterNumber] = useState("");
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadCatalog() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/chapters`, {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(
            await responseError(response, "Unable to load the chapter catalog."),
          );
        }

        const catalog = (await response.json()) as CatalogResponse;
        if (cancelled) {
          return;
        }

        setNovels(catalog.novels);
        const preferredNovel = catalog.novels.find(
          (novel) => novel.novel_name === preferredAfterSelection?.novelName,
        );
        const preferredChapter = preferredNovel?.chapters.find(
          (chapter) =>
            chapter.chapter_number >
            (preferredAfterSelection?.chapterNumber ?? Number.MAX_SAFE_INTEGER),
        );
        const initialNovel = preferredChapter
          ? preferredNovel
          : catalog.novels[0];
        const initialChapter = preferredChapter ?? initialNovel?.chapters[0];
        setNovelName(initialNovel?.novel_name ?? "");
        setChapterNumber(String(initialChapter?.chapter_number ?? ""));
      } catch (catalogError) {
        if (!cancelled) {
          setError(
            catalogError instanceof Error
              ? catalogError.message
              : "Unable to load the chapter catalog.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoadingCatalog(false);
        }
      }
    }

    void loadCatalog();
    return () => {
      cancelled = true;
    };
  }, [preferredAfterSelection]);

  const selectedNovel = useMemo(
    () => novels.find((novel) => novel.novel_name === novelName),
    [novelName, novels],
  );
  const selectedChapter = selectedNovel?.chapters.find(
    (chapter) => String(chapter.chapter_number) === chapterNumber,
  );
  const selection =
    selectedChapter && novelName
      ? { novelName, chapterNumber: selectedChapter.chapter_number }
      : null;

  function selectNovel(nextNovelName: string) {
    const nextNovel = novels.find(
      (novel) => novel.novel_name === nextNovelName,
    );
    setNovelName(nextNovelName);
    setChapterNumber(String(nextNovel?.chapters[0]?.chapter_number ?? ""));
    setError(null);
  }

  async function startWorkflow() {
    if (!selection || selectedChapter?.translated) {
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/workflow/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          novel_name: selection.novelName,
          chapter_number: selection.chapterNumber,
        }),
      });
      if (!response.ok) {
        throw new Error(
          await responseError(response, "Unable to start the workflow."),
        );
      }

      const body = (await response.json()) as { workflow_id: string };
      onWorkflowStarted(body.workflow_id, selection);
    } catch (startError) {
      setError(
        startError instanceof Error
          ? startError.message
          : "Unable to start the workflow.",
      );
      setSubmitting(false);
    }
  }

  return (
    <section className={styles.panel} aria-labelledby="start-title">
      <div className={styles.intro}>
        <p className={styles.eyebrow}>Chapter workspace</p>
        <h2 id="start-title">Select a chapter</h2>
        <p>
          Start a new translation or open a completed chapter for comparison.
        </p>
      </div>

      {loadingCatalog ? (
        <p className={styles.notice} role="status">
          Loading chapter catalog...
        </p>
      ) : novels.length === 0 && !error ? (
        <p className={styles.notice}>
          No raw chapters are currently available.
        </p>
      ) : (
        <div className={styles.controls}>
          <label>
            <span>Novel</span>
            <select
              value={novelName}
              onChange={(event) => selectNovel(event.target.value)}
              disabled={submitting}
            >
              {novels.map((novel) => (
                <option value={novel.novel_name} key={novel.novel_name}>
                  {novel.novel_name}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>Chapter</span>
            <select
              value={chapterNumber}
              onChange={(event) => {
                setChapterNumber(event.target.value);
                setError(null);
              }}
              disabled={!selectedNovel || submitting}
            >
              {selectedNovel?.chapters.map((chapter) => (
                <option
                  value={chapter.chapter_number}
                  key={chapter.chapter_number}
                >
                  Chapter {chapter.chapter_number} ·{" "}
                  {chapter.translated ? "Translated" : "Untranslated"}
                </option>
              ))}
            </select>
          </label>

          <button
            className={styles.primaryAction}
            type="button"
            disabled={!selection || submitting}
            onClick={() => {
              if (!selection) {
                return;
              }
              if (selectedChapter?.translated) {
                onOpenChapter(selection);
              } else {
                void startWorkflow();
              }
            }}
          >
            {submitting
              ? "Starting..."
              : selectedChapter?.translated
                ? "Open read-only"
                : "Start translation"}
          </button>
        </div>
      )}

      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
