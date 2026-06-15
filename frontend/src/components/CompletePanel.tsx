import type { ChapterSelection } from "./StartPanel";
import styles from "./CompletePanel.module.css";

type CompletePanelProps = {
  selection: ChapterSelection;
  onOpenChapter: () => void;
  onStartNextChapter: () => void;
};

export default function CompletePanel({
  selection,
  onOpenChapter,
  onStartNextChapter,
}: CompletePanelProps) {
  return (
    <section className={styles.panel} aria-labelledby="complete-title">
      <div className={styles.successMark} aria-hidden="true">
        ✓
      </div>
      <p className={styles.eyebrow}>Pipeline complete</p>
      <h2 id="complete-title">Translation approved and saved</h2>
      <p className={styles.summary}>
        The completed translation is ready for read-only comparison.
      </p>

      <dl className={styles.receipt}>
        <div>
          <dt>Novel</dt>
          <dd>{selection.novelName}</dd>
        </div>
        <div>
          <dt>Chapter</dt>
          <dd>{selection.chapterNumber}</dd>
        </div>
        <div>
          <dt>Pipeline state</dt>
          <dd>Complete</dd>
        </div>
      </dl>

      <div className={styles.actions}>
        <button
          className={styles.primaryButton}
          type="button"
          onClick={onOpenChapter}
        >
          Open translated chapter
        </button>
        <button
          className={styles.secondaryButton}
          type="button"
          onClick={onStartNextChapter}
        >
          Start next chapter
        </button>
      </div>
    </section>
  );
}
