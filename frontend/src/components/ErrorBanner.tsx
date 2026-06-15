"use client";

import { useState } from "react";

import styles from "./ErrorBanner.module.css";

type ErrorBannerProps = {
  errorCode: string | null;
  errorDetail: string;
  finalText: string | null;
  onRetrySave: () => Promise<void>;
  onStartOver: () => void;
};

export default function ErrorBanner({
  errorCode,
  errorDetail,
  finalText,
  onRetrySave,
  onStartOver,
}: ErrorBannerProps) {
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  async function retrySave() {
    setRetrying(true);
    setRetryError(null);
    try {
      await onRetrySave();
    } catch (error) {
      setRetryError(
        error instanceof Error ? error.message : "Unable to retry the save.",
      );
      setRetrying(false);
    }
  }

  return (
    <section className={styles.banner} aria-labelledby="error-title" role="alert">
      <p className={styles.eyebrow}>Workflow stopped</p>
      <h2 id="error-title">
        {errorCode === "save_conflict"
          ? "A different translation already exists"
          : "Translation could not continue"}
      </h2>
      <p className={styles.detail}>{errorDetail}</p>
      {finalText ? (
        <div className={styles.preservedText}>
          <label htmlFor="preserved-final-text">Preserved final text</label>
          <textarea
            id="preserved-final-text"
            readOnly
            value={finalText}
          />
        </div>
      ) : null}
      <div className={styles.actions}>
        {errorCode === "save_failed" ? (
          <button
            className={styles.retryButton}
            type="button"
            disabled={retrying}
            onClick={() => void retrySave()}
          >
            {retrying ? "Retrying save..." : "Retry save"}
          </button>
        ) : null}
        <button
          className={styles.startOverButton}
          type="button"
          disabled={retrying}
          onClick={onStartOver}
        >
          Start over
        </button>
      </div>
      {retryError ? (
        <p className={styles.retryError} role="alert">
          {retryError}
        </p>
      ) : null}
    </section>
  );
}
