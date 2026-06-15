"use client";

import { useState } from "react";

import CompletePanel from "./CompletePanel";
import ErrorBanner from "./ErrorBanner";
import FinalReview from "./FinalReview";
import GlossaryReview from "./GlossaryReview";
import LoadingPanel from "./LoadingPanel";
import ReadOnlyChapter from "./ReadOnlyChapter";
import StartPanel, { type ChapterSelection } from "./StartPanel";
import StatusBar from "./StatusBar";
import styles from "./Workspace.module.css";
import { useWorkflow } from "../hooks/useWorkflow";

type ChapterDetail = {
  novel_name: string;
  chapter_number: number;
  raw_chinese_text: string;
  translated_text: string;
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function Workspace() {
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [selection, setSelection] = useState<ChapterSelection | null>(null);
  const [chapter, setChapter] = useState<ChapterDetail | null>(null);
  const [chapterError, setChapterError] = useState<string | null>(null);
  const [loadingChapter, setLoadingChapter] = useState(false);
  const [cancellingWorkflow, setCancellingWorkflow] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [preferredAfterSelection, setPreferredAfterSelection] =
    useState<ChapterSelection | null>(null);
  const { status, payload, error, refresh } = useWorkflow(workflowId);

  async function openChapter(nextSelection: ChapterSelection) {
    setSelection(nextSelection);
    setLoadingChapter(true);
    setChapterError(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/chapters/${encodeURIComponent(nextSelection.novelName)}/${nextSelection.chapterNumber}`,
        { cache: "no-store" },
      );
      const body = (await response.json()) as ChapterDetail & { detail?: string };
      if (!response.ok) {
        throw new Error(body.detail ?? "Unable to load the translated chapter.");
      }
      setChapter(body);
    } catch (openError) {
      setChapterError(
        openError instanceof Error
          ? openError.message
          : "Unable to load the translated chapter.",
      );
    } finally {
      setLoadingChapter(false);
    }
  }

  function backToSelection() {
    setChapter(null);
    setChapterError(null);
    setSelection(null);
    setPreferredAfterSelection(null);
  }

  function clearWorkflowState() {
    setWorkflowId(null);
    setSelection(null);
    setChapter(null);
    setChapterError(null);
    setLoadingChapter(false);
    setCancellingWorkflow(false);
    setCancelError(null);
    setPreferredAfterSelection(null);
  }

  async function cancelWorkflow() {
    if (!workflowId) {
      return;
    }

    if (
      !window.confirm(
        "Cancel this workflow? Current workflow state will be discarded.",
      )
    ) {
      return;
    }

    setCancellingWorkflow(true);
    setCancelError(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/workflow/${workflowId}/kill`,
        { method: "POST" },
      );
      if (!response.ok) {
        const body = (await response.json()) as { detail?: string };
        throw new Error(body.detail ?? "Unable to cancel workflow.");
      }
      clearWorkflowState();
    } catch (cancelFailure) {
      setCancelError(
        cancelFailure instanceof Error
          ? cancelFailure.message
          : "Unable to cancel workflow.",
      );
      setCancellingWorkflow(false);
    }
  }

  async function retrySave() {
    if (!workflowId) {
      return;
    }

    const response = await fetch(
      `${API_BASE_URL}/api/workflow/${workflowId}/retry-save`,
      { method: "POST" },
    );
    if (!response.ok) {
      const body = (await response.json()) as { detail?: string };
      refresh();
      throw new Error(body.detail ?? "Unable to retry the save.");
    }
    refresh();
  }

  const contextLabel = selection
    ? `${selection.novelName} · Chapter ${selection.chapterNumber}`
    : null;

  function renderActiveWorkflowPanel() {
    if (!workflowId) {
      return null;
    }

    if (status === "glossary_review" && payload?.glossary_terms) {
      return (
        <GlossaryReview
          terms={payload.glossary_terms}
          workflowId={workflowId}
        />
      );
    }

    if (
      status === "final_review" &&
      payload?.raw_chinese_text &&
      payload.edited_text &&
      selection
    ) {
      return (
        <FinalReview
          key={`${workflowId}-${payload.editor_revision ?? 0}`}
          chapterNumber={selection.chapterNumber}
          editedText={payload.edited_text}
          novelName={selection.novelName}
          rawChineseText={payload.raw_chinese_text}
          warnings={payload.warnings}
          workflowId={workflowId}
        />
      );
    }

    if (status === "complete" && selection) {
      return (
        <CompletePanel
          selection={selection}
          onOpenChapter={() => {
            const completedSelection = selection;
            clearWorkflowState();
            void openChapter(completedSelection);
          }}
          onStartNextChapter={() => {
            const completedSelection = selection;
            clearWorkflowState();
            setSelection(null);
            setPreferredAfterSelection(completedSelection);
          }}
        />
      );
    }

    if (status === "error" || error) {
      return (
        <ErrorBanner
          errorCode={payload?.error_code ?? null}
          errorDetail={error ?? "The workflow stopped unexpectedly."}
          finalText={payload?.final_text ?? null}
          onRetrySave={retrySave}
          onStartOver={clearWorkflowState}
        />
      );
    }

    return <LoadingPanel status={status} />;
  }

  return (
    <main className={styles.workspace} aria-label="AI Novel Translation">
      <header className={styles.header}>
        <div>
          <p className={styles.productLabel}>AI Novel Translation</p>
          <h1>Translation Review</h1>
        </div>
        <div className={styles.headerActions}>
          {contextLabel ? <p className={styles.context}>{contextLabel}</p> : null}
          {workflowId ? (
            <button
              className={styles.cancelWorkflowButton}
              type="button"
              disabled={cancellingWorkflow}
              onClick={() => void cancelWorkflow()}
            >
              {cancellingWorkflow ? "Cancelling..." : "Cancel workflow"}
            </button>
          ) : null}
        </div>
      </header>

      {workflowId ? (
        <>
          {cancelError ? (
            <p className={styles.cancelError} role="alert">
              {cancelError}
            </p>
          ) : null}
          <StatusBar status={status} />
          {renderActiveWorkflowPanel()}
        </>
      ) : chapter || loadingChapter || chapterError ? (
        <ReadOnlyChapter
          error={chapterError}
          loading={loadingChapter}
          onBack={backToSelection}
          rawChineseText={chapter?.raw_chinese_text ?? null}
          translatedText={chapter?.translated_text ?? null}
        />
      ) : (
        <StartPanel
          onOpenChapter={(nextSelection) => void openChapter(nextSelection)}
          onWorkflowStarted={(nextWorkflowId, nextSelection) => {
            setPreferredAfterSelection(null);
            setSelection(nextSelection);
            setWorkflowId(nextWorkflowId);
          }}
          preferredAfterSelection={preferredAfterSelection}
        />
      )}
    </main>
  );
}
