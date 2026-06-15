"use client";

import { useEffect, useState } from "react";

export type GlossaryTerm = {
  term_key: string;
  chinese: string;
  proposed_english: string;
  description: string;
  approved_english: string | null;
  status: string;
  is_new: boolean;
};

export type WorkflowPayload = {
  glossary_terms: GlossaryTerm[] | null;
  raw_chinese_text: string | null;
  edited_text: string | null;
  editor_revision: number | null;
  final_text: string | null;
  error_stage: string | null;
  error_code: string | null;
  warnings: string[];
};

type WorkflowStatusResponse = WorkflowPayload & {
  status: string;
  error_detail: string | null;
};

type UseWorkflowResult = {
  status: string | null;
  payload: WorkflowPayload | null;
  error: string | null;
  refresh: () => void;
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TERMINAL_STATUSES = new Set(["complete", "error"]);

function getErrorMessage(body: unknown, fallback: string) {
  if (
    body &&
    typeof body === "object" &&
    "detail" in body &&
    typeof body.detail === "string"
  ) {
    return body.detail;
  }

  return fallback;
}

export function useWorkflow(workflowId: string | null): UseWorkflowResult {
  const [status, setStatus] = useState<string | null>(null);
  const [payload, setPayload] = useState<WorkflowPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);

  useEffect(() => {
    setStatus(null);
    setPayload(null);
    setError(null);

    if (!workflowId) {
      return;
    }

    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/workflow/${workflowId}/status`,
          { cache: "no-store" },
        );
        const body: unknown = await response.json();

        if (!response.ok) {
          throw new Error(
            getErrorMessage(body, "Unable to load workflow status."),
          );
        }

        const workflow = body as WorkflowStatusResponse;
        if (cancelled) {
          return;
        }

        setStatus(workflow.status);
        setPayload({
          glossary_terms: workflow.glossary_terms,
          raw_chinese_text: workflow.raw_chinese_text,
          edited_text: workflow.edited_text,
          editor_revision: workflow.editor_revision,
          final_text: workflow.final_text,
          error_stage: workflow.error_stage,
          error_code: workflow.error_code,
          warnings: workflow.warnings ?? [],
        });
        setError(
          workflow.status === "error"
            ? workflow.error_detail ?? "The workflow stopped unexpectedly."
            : null,
        );

        if (!TERMINAL_STATUSES.has(workflow.status)) {
          timeoutId = setTimeout(poll, 2000);
        }
      } catch (pollError) {
        if (!cancelled) {
          setError(
            pollError instanceof Error
              ? pollError.message
              : "Unable to load workflow status.",
          );
        }
      }
    }

    void poll();

    return () => {
      cancelled = true;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [refreshVersion, workflowId]);

  return {
    status,
    payload,
    error,
    refresh: () => setRefreshVersion((current) => current + 1),
  };
}
