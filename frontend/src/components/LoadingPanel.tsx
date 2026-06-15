"use client";

import { useEffect, useState } from "react";

import styles from "./LoadingPanel.module.css";

type LoadingPanelProps = {
  status: string | null;
};

const STAGE_DETAILS: Record<string, { description: string; label: string }> = {
  pending: {
    label: "Preparing workflow",
    description: "The translation workflow is starting.",
  },
  fetching: {
    label: "Fetching chapter",
    description: "Loading the raw Chinese chapter from storage.",
  },
  translating: {
    label: "Translating chapter",
    description: "Creating the first English translation using approved terms.",
  },
  editing: {
    label: "Editing translation",
    description: "Refining the translation for consistency and readability.",
  },
  saving: {
    label: "Saving translation",
    description: "Saving the human-approved final translation.",
  },
};

function formatElapsed(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
}

export default function LoadingPanel({ status }: LoadingPanelProps) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const stage = STAGE_DETAILS[status ?? "pending"] ?? STAGE_DETAILS.pending;
  const showSpinner = ["fetching", "translating", "editing", "saving"].includes(
    status ?? "",
  );

  useEffect(() => {
    setElapsedSeconds(0);
    const intervalId = window.setInterval(
      () => setElapsedSeconds((current) => current + 1),
      1000,
    );
    return () => window.clearInterval(intervalId);
  }, [status]);

  return (
    <section className={styles.panel} aria-labelledby="loading-title">
      {showSpinner ? <span className={styles.spinner} aria-hidden="true" /> : null}
      <p className={styles.eyebrow}>Workflow active</p>
      <h2 id="loading-title">{stage.label}</h2>
      <p className={styles.description}>{stage.description}</p>
      <p className={styles.elapsed} role="timer">
        Elapsed time <strong>{formatElapsed(elapsedSeconds)}</strong>
      </p>
    </section>
  );
}
