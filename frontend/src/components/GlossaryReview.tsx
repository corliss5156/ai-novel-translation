"use client";

import { useEffect, useState } from "react";

import type { GlossaryTerm } from "../hooks/useWorkflow";
import styles from "./GlossaryReview.module.css";

type DecisionAction = "approve" | "reject" | null;

type ReviewTerm = GlossaryTerm & {
  action: DecisionAction;
  english: string;
};

type AddedTerm = {
  id: number;
  chinese: string;
  approvedEnglish: string;
};

type GlossaryReviewProps = {
  terms: GlossaryTerm[];
  workflowId: string;
};

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

export default function GlossaryReview({
  terms,
  workflowId,
}: GlossaryReviewProps) {
  const termSignature = terms
    .map((term) => `${term.term_key}:${term.proposed_english}`)
    .join("|");
  const [reviewTerms, setReviewTerms] = useState<ReviewTerm[]>([]);
  const [addedTerms, setAddedTerms] = useState<AddedTerm[]>([]);
  const [nextAddedId, setNextAddedId] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setReviewTerms(
      terms.map((term) => ({
        ...term,
        action: null,
        english: term.proposed_english,
      })),
    );
    setAddedTerms([]);
    setNextAddedId(1);
    setSubmitting(false);
    setSubmitted(false);
    setError(null);
  }, [termSignature, workflowId]);

  function updateReviewTerm(
    termKey: string,
    update: Partial<Pick<ReviewTerm, "action" | "english">>,
  ) {
    setReviewTerms((current) =>
      current.map((term) =>
        term.term_key === termKey ? { ...term, ...update } : term,
      ),
    );
    setError(null);
  }

  function approveAll() {
    setReviewTerms((current) =>
      current.map((term) => ({ ...term, action: "approve" })),
    );
    setError(null);
  }

  function addTerm() {
    setAddedTerms((current) => [
      ...current,
      { id: nextAddedId, chinese: "", approvedEnglish: "" },
    ]);
    setNextAddedId((current) => current + 1);
  }

  function updateAddedTerm(
    id: number,
    update: Partial<Pick<AddedTerm, "chinese" | "approvedEnglish">>,
  ) {
    setAddedTerms((current) =>
      current.map((term) => (term.id === id ? { ...term, ...update } : term)),
    );
    setError(null);
  }

  function validate() {
    if (reviewTerms.some((term) => term.action === null)) {
      return "Approve or reject every extracted term before submitting.";
    }
    if (
      reviewTerms.some(
        (term) => term.action === "approve" && !term.english.trim(),
      )
    ) {
      return "Every approved term needs an English translation.";
    }
    if (
      addedTerms.some(
        (term) => !term.chinese.trim() || !term.approvedEnglish.trim(),
      )
    ) {
      return "Every added term needs both Chinese and approved English values.";
    }

    const termKeys = [
      ...reviewTerms.map((term) => term.term_key.trim()),
      ...addedTerms.map((term) => term.chinese.trim()),
    ];
    if (new Set(termKeys).size !== termKeys.length) {
      return "Glossary terms must have unique Chinese values.";
    }

    return null;
  }

  async function submitReview() {
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/review/glossary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workflow_id: workflowId,
          decisions: reviewTerms.map((term) => ({
            term_key: term.term_key,
            action: term.action,
            approved_english:
              term.action === "approve" ? term.english.trim() : null,
          })),
          suggestions: addedTerms.map((term) => ({
            chinese: term.chinese.trim(),
            approved_english: term.approvedEnglish.trim(),
          })),
        }),
      });
      if (!response.ok) {
        throw new Error(
          await responseError(response, "Unable to submit glossary review."),
        );
      }
      setSubmitted(true);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Unable to submit glossary review.",
      );
      setSubmitting(false);
    }
  }

  const locked = submitting || submitted;

  return (
    <section className={styles.panel} aria-labelledby="glossary-title">
      <div className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Human review checkpoint</p>
          <h2 id="glossary-title">Review glossary terms</h2>
          <p>
            Confirm, edit, or reject every extracted proposal before translation.
          </p>
        </div>
        <div className={styles.headerActions}>
          <button
            className={styles.secondaryButton}
            type="button"
            onClick={approveAll}
            disabled={locked || reviewTerms.length === 0}
          >
            Approve all proposals
          </button>
          <button
            className={styles.secondaryButton}
            type="button"
            onClick={addTerm}
            disabled={locked}
          >
            Add term
          </button>
        </div>
      </div>

      <div className={styles.termList}>
        {reviewTerms.map((term) => (
          <article className={styles.termCard} key={term.term_key}>
            <div className={styles.termDetails}>
              <div>
                <span className={styles.fieldLabel}>Chinese term</span>
                <strong lang="zh">{term.chinese}</strong>
              </div>
              <p>{term.description || "No context description provided."}</p>
            </div>

            <label className={styles.englishField}>
              <span>English translation</span>
              <input
                type="text"
                value={term.english}
                disabled={locked}
                onChange={(event) =>
                  updateReviewTerm(term.term_key, {
                    english: event.target.value,
                  })
                }
              />
            </label>

            <div className={styles.decisionGroup} aria-label={`Decision for ${term.chinese}`}>
              <button
                className={term.action === "approve" ? styles.approved : ""}
                type="button"
                disabled={locked}
                aria-pressed={term.action === "approve"}
                onClick={() =>
                  updateReviewTerm(term.term_key, { action: "approve" })
                }
              >
                Approve
              </button>
              <button
                className={term.action === "reject" ? styles.rejected : ""}
                type="button"
                disabled={locked}
                aria-pressed={term.action === "reject"}
                onClick={() =>
                  updateReviewTerm(term.term_key, { action: "reject" })
                }
              >
                Reject
              </button>
              <span className={styles.decisionStatus}>
                {term.action ?? "Unresolved"}
              </span>
            </div>
          </article>
        ))}
      </div>

      {addedTerms.length > 0 ? (
        <section className={styles.addedSection} aria-labelledby="added-title">
          <div>
            <h3 id="added-title">Reviewer-added terms</h3>
            <p>Added terms are automatically approved when submitted.</p>
          </div>
          <div className={styles.addedList}>
            {addedTerms.map((term, index) => (
              <div className={styles.addedRow} key={term.id}>
                <label>
                  <span>Chinese term {index + 1}</span>
                  <input
                    type="text"
                    value={term.chinese}
                    disabled={locked}
                    onChange={(event) =>
                      updateAddedTerm(term.id, { chinese: event.target.value })
                    }
                  />
                </label>
                <label>
                  <span>Approved English</span>
                  <input
                    type="text"
                    value={term.approvedEnglish}
                    disabled={locked}
                    onChange={(event) =>
                      updateAddedTerm(term.id, {
                        approvedEnglish: event.target.value,
                      })
                    }
                  />
                </label>
                <button
                  className={styles.removeButton}
                  type="button"
                  disabled={locked}
                  onClick={() =>
                    setAddedTerms((current) =>
                      current.filter((candidate) => candidate.id !== term.id),
                    )
                  }
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}

      <footer className={styles.footer}>
        <p>
          {reviewTerms.filter((term) => term.action !== null).length} of{" "}
          {reviewTerms.length} extracted terms resolved
        </p>
        <button
          className={styles.submitButton}
          type="button"
          disabled={locked}
          onClick={() => void submitReview()}
        >
          {submitted || submitting ? "Submitting review..." : "Submit review"}
        </button>
      </footer>
    </section>
  );
}
