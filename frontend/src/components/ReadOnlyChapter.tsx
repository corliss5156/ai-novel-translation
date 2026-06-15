import styles from "./ReadOnlyChapter.module.css";

type ReadOnlyChapterProps = {
  error: string | null;
  loading: boolean;
  onBack: () => void;
  rawChineseText: string | null;
  translatedText: string | null;
};

export default function ReadOnlyChapter({
  error,
  loading,
  onBack,
  rawChineseText,
  translatedText,
}: ReadOnlyChapterProps) {
  return (
    <section className={styles.view} aria-labelledby="read-only-title">
      <header className={styles.toolbar}>
        <div>
          <p>Read-only comparison</p>
          <h2 id="read-only-title">Translated chapter</h2>
        </div>
        <button type="button" onClick={onBack}>
          Back to chapter selection
        </button>
      </header>

      {loading ? (
        <p className={styles.notice} role="status">
          Loading translated chapter...
        </p>
      ) : null}

      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}

      {!loading && !error && rawChineseText !== null && translatedText !== null ? (
        <div className={styles.readers}>
          <article>
            <header>
              <span>Source</span>
              <h3>Raw Chinese</h3>
            </header>
            <pre lang="zh">{rawChineseText}</pre>
          </article>
          <article>
            <header>
              <span>Translation</span>
              <h3>Saved English</h3>
            </header>
            <pre>{translatedText}</pre>
          </article>
        </div>
      ) : null}
    </section>
  );
}
