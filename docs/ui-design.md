# Translation Review UI Design

## Purpose

Build a desktop-first interface for an internal translator or editor to translate
and review one novel chapter at a time. The interface must make long-form text
easy to read, keep the current workflow state clear, and preserve explicit human
approval at both review checkpoints.

The visual direction is a clean, neutral enterprise dashboard. Use white and
light-gray surfaces, high-contrast dark text, restrained blue for active states,
amber for warnings, and red for destructive actions. Avoid decorative wuxia
styling, paper textures, and ink-inspired typography.

## Product Scope

- One active translation workflow per browser session.
- Desktop is the primary target, with a comfortable minimum width of 1024px.
- The interface is a single-page persistent workspace.
- Translated chapters can be opened in a read-only comparison view.
- The workflow continues to use the existing two human review checkpoints.
- Frontend acceptance testing is performed manually by the user. No frontend
  automated tests are required for Phase 1.

## Persistent Workspace Shell

Before a chapter is selected, the header shows the product name only. During an
active workflow, it also shows the selected novel and chapter.

Below the header, show a six-stage progress indicator:

1. Fetching
2. Glossary Review
3. Translating
4. Editing
5. Final Review
6. Complete

The active stage must be visually distinct. Completed stages show a completion
state, and future stages remain subdued. The main workspace below the progress
indicator changes according to the current stage.

## Start Screen

The start screen uses two dependent dropdowns:

- **Novel** lists novels returned by the chapter catalog API.
- **Chapter** lists chapters for the selected novel and labels each as
  `Untranslated` or `Translated`.

Selecting an untranslated chapter enables **Start translation**. Selecting a
translated chapter enables **Open read-only**. Translated chapters remain
selectable and must not start a new translation workflow.

Catalog loading, empty catalog, and API failure states appear inline without
leaving the screen.

## Active Processing States

Fetching, Translating, and Editing use a focused loading panel. It shows:

- Current stage name
- Short plain-language description
- Elapsed time
- Secondary **Cancel workflow** action

Cancellation requires confirmation, calls the existing kill endpoint, and
returns the user to chapter selection. The interface does not offer a second
workflow while one is active.

## Glossary Review

Display newly extracted terms as a vertical list of compact review cards. Each
card contains:

- Read-only Chinese term
- Context description
- Editable English translation prefilled with the AI proposal
- Explicit **Approve** and **Reject** controls
- Clear unresolved state until the reviewer chooses a decision

Provide **Approve all proposals** as a bulk action. Provide **Add term** for
terms missed by extraction. A reviewer-added term requires Chinese and approved
English values and is automatically approved when submitted.

Submission remains disabled until every extracted term has an explicit decision
and every approved term has non-empty English text. After submission, controls
lock to prevent duplicate requests. API failures appear inline and preserve all
decisions and edits.

## Final Review

Use a three-column workspace:

- Left: raw Chinese source
- Center: edited English translation
- Right: sticky review action panel

The source and translation panels use readable typography, sticky headers, and
independent scrolling. The review panel shows chapter details and provides:

- **Approve translation**
- **Request revision**
- Revision feedback textarea, shown when revision is selected

Revision feedback must contain at least 10 characters. Both chapter texts are
read-only and rendered as plain text, never raw HTML.

Non-blocking workflow warnings appear in a persistent amber banner above the
reader. Warnings do not prevent approval.

## Completion

After approval, show a success receipt containing the novel, chapter number, and
completed pipeline state. Provide:

- **Open translated chapter**
- **Start next chapter**

Opening the translated chapter uses the same read-only comparison view available
from the start screen.

## Read-Only Chapter View

Display raw Chinese on the left and saved English on the right in equal-width
panels. Each panel scrolls independently and has a sticky header.

This view has no editing, approval, or revision controls. It provides only
**Back to chapter selection**.

## Errors And Warnings

Blocking workflow errors replace the active panel with a concise error summary
and **Start over** action. Do not display raw stack traces. Submission errors
stay inline so reviewer input is not lost.

Non-blocking warnings remain visible in an amber banner within the relevant
review screen until the workflow advances.

## Backend Contract Changes

### Chapter Catalog

Add a read-only endpoint that returns novels and their raw chapters, including
whether each chapter has a translated S3 object. The endpoint is the source of
truth for both dropdowns.

### Read-Only Chapter Detail

Add a read-only endpoint that returns the raw Chinese text and saved English text
for a translated chapter. It must return a clear not-found response when either
required object is unavailable.

### Workflow Status

Extend the workflow status response:

- Return `raw_chinese_text` and `edited_text` during `final_review`.
- Return non-blocking `warnings` while a workflow is active.
- Preserve the existing stage-specific response behavior and avoid returning the
  full workflow state.

The existing kill endpoint powers workflow cancellation.

## Accessibility And Readability

- Use visible labels for all controls.
- Provide clear keyboard focus states.
- Maintain sufficient color contrast.
- Keep prose line length and line spacing comfortable for long-form reading.
- Do not rely on color alone for statuses or decisions.
- Keep destructive actions visually secondary until intentionally selected.

## Manual Acceptance Checklist

- Novel selection filters the chapter dropdown.
- Chapters show correct `Translated` or `Untranslated` labels.
- Translated chapters open the read-only comparison view.
- Untranslated chapters start a workflow.
- Progress accurately reflects each workflow stage.
- Cancellation confirms intent and returns to chapter selection.
- Glossary proposals are prefilled but require explicit decisions.
- Bulk approval and reviewer-added terms submit correctly.
- Invalid glossary decisions remain blocked with inline guidance.
- Final review shows source, translation, warnings, and sticky actions.
- Revision requires at least 10 characters of feedback.
- Submission failures preserve reviewer input.
- Approval shows the success receipt.
- Completed chapters can be opened read-only from both completion and start.
- Blocking errors show a concise message and start-over action.

