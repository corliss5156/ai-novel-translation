import styles from "./StatusBar.module.css";

type StatusBarProps = {
  status: string | null;
};

const STAGES = [
  { status: "fetching", label: "Fetching" },
  { status: "glossary_review", label: "Glossary review" },
  { status: "translating", label: "Translating" },
  { status: "editing", label: "Editing" },
  { status: "final_review", label: "Final review" },
  { status: "saving", label: "Saving" },
  { status: "complete", label: "Complete" },
];

function activeStageIndex(status: string | null) {
  if (status === "pending") {
    return 0;
  }

  if (status === "error") {
    return -1;
  }

  return STAGES.findIndex((stage) => stage.status === status);
}

export default function StatusBar({ status }: StatusBarProps) {
  const activeIndex = activeStageIndex(status);

  return (
    <nav className={styles.statusBar} aria-label="Translation progress">
      <ol className={styles.stageList}>
        {STAGES.map((stage, index) => {
          const isActive = index === activeIndex;
          const isComplete =
            status === "complete" || (activeIndex >= 0 && index < activeIndex);

          return (
            <li
              className={[
                styles.stage,
                isActive ? styles.active : "",
                isComplete ? styles.complete : "",
              ]
                .filter(Boolean)
                .join(" ")}
              aria-current={isActive ? "step" : undefined}
              key={stage.status}
            >
              <span className={styles.marker} aria-hidden="true">
                {isComplete ? "✓" : index + 1}
              </span>
              <span>{stage.label}</span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
