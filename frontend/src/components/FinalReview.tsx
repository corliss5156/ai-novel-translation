"use client";

import { useState } from "react";

import styles from "./FinalReview.module.css";

type FinalReviewProps = {
  chapterNumber: number;
  editedText: string;
  novelName: string;
  rawChineseText: string;
  warnings: string[];
  workflowId: string;
};

type ReviewMode = "ai-review" | "manual-editing";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function responseError(response: Response, fallback: string) {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? fallback;
  } catch {
    return fallback;
  }
}

export default function FinalReview({
  chapterNumber,
  editedText,
  novelName,
  rawChineseText,
  warnings,
  workflowId,
}: FinalReviewProps) {
  const [mode, setMode] = useState<ReviewMode>("ai-review");
  const [finalText, setFinalText] = useState(editedText);
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function approveFinalText() {
    if (!finalText.trim()) {
      setError("Final translation must not be blank.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/review/final`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workflow_id: workflowId,
          final_text: finalText,
        }),
      });
      if (!response.ok) {
        throw new Error(
          await responseError(response, "Unable to submit final review."),
        );
      }
      setSubmitted(true);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Unable to submit final review.",
      );
      setSubmitting(false);
    }
  }

  async function requestEditorRevision() {
    if (feedback.trim().length < 10) {
      setError("Editor revision feedback must contain at least 10 characters.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/review/editor`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workflow_id: workflowId,
          feedback: feedback.trim(),
        }),
      });
      if (!response.ok) {
        throw new Error(
          await responseError(response, "Unable to request editor revision."),
        );
      }
      setSubmitted(true);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Unable to request editor revision.",
      );
      setSubmitting(false);
    }
  }

  const locked = submitting || submitted;

  return (
    <section className={styles.panel} aria-labelledby="final-review-title">
      <div className={styles.heading}>
        <p className={styles.eyebrow}>Human review checkpoint</p>
        <h2 id="final-review-title">Final translation review</h2>
        <p>
          {mode === "ai-review"
            ? "Review the AI-edited translation before beginning manual edits."
            : "Make final manual edits and approve the text for saving."}
        </p>
      </div>

      {warnings.length > 0 ? (
        <aside className={styles.warningBanner} aria-label="Workflow warnings">
          <strong>Review warnings</strong>
          <ul>
            {warnings.map((warning, index) => (
              <li key={`${warning}-${index}`}>{warning}</li>
            ))}
          </ul>
        </aside>
      ) : null}

      <div className={styles.reviewGrid}>
        <article className={styles.reader}>
          <header>
            <span>Source</span>
            <h3>Raw Chinese</h3>
          </header>
          <pre lang="zh">{rawChineseText}</pre>
        </article>

        <article
          className={`${styles.reader} ${
            mode === "manual-editing" ? styles.translationReader : ""
          }`}
        >
          <header>
            <span>Translation</span>
            <h3>{mode === "ai-review" ? "AI Edited English" : "Final English"}</h3>
          </header>
          {mode === "ai-review" ? (
            <pre>{editedText}</pre>
          ) : (
            <textarea
              aria-label="Final English translation"
              className={styles.translationEditor}
              disabled={locked}
              value={finalText}
              onChange={(event) => {
                setFinalText(event.target.value);
                setError(null);
              }}
            />
          )}
        </article>

        <aside className={styles.actions}>
          <p className={styles.actionLabel}>Chapter details</p>
          <dl>
            <div>
              <dt>Novel</dt>
              <dd>{novelName}</dd>
            </div>
            <div>
              <dt>Chapter</dt>
              <dd>{chapterNumber}</dd>
            </div>
          </dl>

          {mode === "ai-review" ? (
            <>
              <button
                className={styles.reviseButton}
                type="button"
                disabled={locked}
                aria-expanded={showFeedback}
                onClick={() => {
                  setShowFeedback(true);
                  setError(null);
                }}
              >
                Request AI revision
              </button>
              {showFeedback ? (
                <div className={styles.feedback}>
                  <label htmlFor="editor-feedback">Editor feedback</label>
                  <textarea
                    id="editor-feedback"
                    disabled={locked}
                    minLength={10}
                    rows={7}
                    value={feedback}
                    onChange={(event) => {
                      setFeedback(event.target.value);
                      setError(null);
                    }}
                    placeholder="Describe the changes needed in at least 10 characters."
                  />
                  <span>{feedback.trim().length} / 10 minimum</span>
                  <button
                    className={styles.submitRevisionButton}
                    type="button"
                    disabled={locked || feedback.trim().length < 10}
                    onClick={() => void requestEditorRevision()}
                  >
                    {locked ? "Requesting revision..." : "Submit revision request"}
                  </button>
                </div>
              ) : null}
              <button
                className={styles.manualEditButton}
                type="button"
                disabled={locked}
                onClick={() => {
                  setMode("manual-editing");
                  setShowFeedback(false);
                  setError(null);
                }}
              >
                Start manual editing
              </button>
            </>
          ) : (
            <button
              className={styles.approveButton}
              type="button"
              disabled={locked || !finalText.trim()}
              onClick={() => void approveFinalText()}
            >
              {locked ? "Approving translation..." : "Approve translation"}
            </button>
          )}

          {error ? (
            <p className={styles.error} role="alert">
              {error}
            </p>
          ) : null}
        </aside>
      </div>
    </section>
  );
}
