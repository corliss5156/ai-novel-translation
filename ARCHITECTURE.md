# Wuxia Translation AI — Architecture Specification

---

## Project Overview

An AI-orchestrated pipeline that translates wuxia novels from Chinese to English. The system combines LLM agents, human-in-the-loop review checkpoints, a persistent glossary database, and cloud storage — coordinated by a LangGraph state machine.

**Entry point:** User submits `novel name` + `chapter number` via the web UI
**Exit point:** Approved English translation saved to S3

---

## Orchestration Framework

**LangGraph** (by the LangChain team).

LangGraph was chosen over alternatives (CrewAI, AutoGen) for the following reasons:

- Human-in-the-loop interrupts are a first-class primitive (`interrupt()`), not bolted on
- The workflow is an explicit directed graph — every node and edge is visible in code
- State is a single typed dict passed between all nodes, making data flow auditable
- Crash recovery and resumability are built into the checkpointing model (phase 2)
- The abstraction level rewards understanding: interviewers can ask "walk me through your architecture" and the code matches the answer

**Model:** `claude-sonnet-4-20250514` across all LLM nodes. A shared singleton client is used — see `llm/client.py`. Per-node model selection is a phase 2 improvement.

---

## System State Object

The state object is the single source of truth passed between every node in the graph. It is defined as a `TypedDict` in `graph/state.py` and mutated by nodes — never replaced wholesale.

```python
from typing import TypedDict, Optional, List

class GlossaryTerm(TypedDict):
    chinese:           str        # original Chinese term
    proposed_english:  str        # LLM suggestion
    approved_english:  str | None # human-settled translation
    status:            str        # "pending_review" | "approved" | "rejected"
    is_new:            bool       # True = discovered this chapter

class WorkflowState(TypedDict):
    # --- Inputs ---
    workflow_id:       str        # UUID generated at workflow start
    novel_name:        str        # e.g. "legendary-moonlight-sculptor"
    chapter_number:    int        # e.g. 5

    # --- Workflow status ---
    # Possible values:
    #   pending → fetching → glossary_review → translating
    #   → editing → final_review → complete | error
    status:            str

    # --- Retrieval ---
    raw_chinese_text:  str        # fetched from S3, immutable after retrieval

    # --- Glossary ---
    # Loaded from DB at glossary extraction time; agents read from here only
    glossary_terms:    List[GlossaryTerm]

    # --- Translation pipeline (three separate versions, never overwritten) ---
    translated_text:   str | None  # raw output from translator LLM
    edited_text:       str | None  # output after editor agent pass
    final_text:        str | None  # human-approved, ready to save

    # --- Human feedback ---
    editor_feedback:   str | None  # human's revision notes fed back to editor

    # --- Error capture ---
    error_detail:      str | None  # set by runner on unhandled exception

    # --- Metadata ---
    created_at:        str         # ISO 8601 UTC timestamp
    completed_at:      str | None  # ISO 8601 UTC timestamp, set on completion
    model_used:        str         # e.g. "claude-sonnet-4-20250514"
```

### Important constraints on state

- `state.py` must be a dependency-free file — do not import LangGraph, SQLAlchemy, or any application module here. It must be importable from anywhere without side effects.
- Use a plain `TypedDict`, not a Pydantic model or dataclass. LangGraph requires TypedDict.
- `status` is typed as `str`, not an `Enum`. LangGraph serialisation does not handle Enum by default.
- `error_detail` is always present on the TypedDict but is `None` unless the runner catches an exception.

### Status update convention

Status is updated at the **start** of each node, not the end. This means if a node crashes mid-execution, the status reflects what the system was *attempting* — enabling precise crash recovery.

```python
def translator_node(state: WorkflowState) -> WorkflowState:
    state["status"] = "translating"   # update first
    result = call_llm(...)
    state["translated_text"] = result
    return state
```

---

## Node Chain

```
[user input: novel_name + chapter_number]
      │
      ▼
[S3 retrieval node]           — fetches raw Chinese text from S3
      │                         Writes: status="fetching", raw_chinese_text
      ▼
[glossary extractor node]     — LLM detects terms, proposes translations
      │                         DB: READ approved+pending terms for this novel
      │                         DB: CREATE new pending_review terms
      │                         Writes: status="glossary_review", glossary_terms
      ▼
[⏸ HITL checkpoint: glossary review]
      │   Human: approve / edit / reject terms via web UI
      │   API: POST /api/review/glossary → writes decisions to state → resume()
      │
      ▼  (loop back to glossary extractor if human rejects entire batch)
[glossary DB write node]      — persist newly approved terms in one bulk insert
      │                         Drops pending/rejected terms from workflow state
      │                         DB: INSERT approved terms with approval chapter
      ▼
[translator node]             — LLM: Chinese → English using glossary in state
      │                         Reads glossary from state only (no DB call)
      │                         Writes: status="translating", translated_text
      ▼
[editor node]                 — LLM: enforce formatting rules (from prompt file)
      │                         Writes: status="editing", edited_text
      ▼
[⏸ HITL checkpoint: final review]
      │   Human: approve or request revision (with feedback notes)
      │   API: POST /api/review/final → writes decision to state → resume()
      │
      ▼  (loop back to editor with editor_feedback if revised)
[complete node]               — S3 CREATE final_text as .md file
                                Writes: status="complete", completed_at
```

---

## Human-in-the-Loop Pattern

Both checkpoints use LangGraph's `interrupt()` primitive. The graph pauses, and waits. The human interacts with the Next.js web UI. The UI calls a FastAPI endpoint. The endpoint writes the human's decision into state and calls LangGraph's `resume()`. The graph continues from the exact node it paused at.

**The human never writes to state directly.** The FastAPI backend is the boundary between the human world and the agent world.

```
Human action in UI
  → POST /api/review/glossary  (or /api/review/final)
    → FastAPI writes decisions into state
      → langgraph.resume(workflow_id)
        → next node runs
```

### Phase 1 constraint

State is held **in-memory only** (module-level dict in `graph/runner.py`). A server restart kills all in-flight workflows. This is acceptable for phase 1 (local dev / demo). A LangGraph Postgres checkpointer for true resumability is a phase 2 improvement.

---

## FastAPI ↔ LangGraph Coupling

LangGraph runs as an `asyncio.create_task` inside the FastAPI process. There is no separate LangGraph server process.

```
FastAPI process
  ├── HTTP request handlers (routes/)
  ├── state_store: dict[workflow_id → WorkflowState]   # module-level
  └── asyncio background tasks (one per active workflow)
        └── graph.ainvoke(state, config={"thread_id": workflow_id})
```

### Runner pattern (graph/runner.py)

The runner wraps every graph invocation in `try/except`. Any unhandled exception from any node writes `status="error"` and `error_detail=str(exc)` to state before re-raising. This guarantees the status polling endpoint never returns a frozen status.

```python
async def run_graph(workflow_id: str, initial_state: WorkflowState):
    try:
        await graph.ainvoke(initial_state, config={"thread_id": workflow_id})
    except Exception as exc:
        state_store[workflow_id]["status"] = "error"
        state_store[workflow_id]["error_detail"] = str(exc)
        raise
```

### Key rules

- Use `asyncio.create_task` only — never `threading.Thread`
- `state_store` is a module-level dict, not a class attribute
- The HTTP response to `POST /api/workflow/start` must return within 200ms — the graph runs entirely in the background and must not block the response

---

## Glossary Behaviour

| Term status | Behaviour at extraction time |
|---|---|
| `approved` | Silently loaded into state. Not shown for re-review. |
| `pending_review` | Held in workflow state and shown to human for review. Never written to DB. |
| `rejected` | Dropped from workflow state after review. Never written to DB. |

The DB read query at glossary extraction time:

```sql
SELECT * FROM glossary
WHERE novel_name = :novel_name
AND status = 'approved';
```

Only approved terms are loaded from the DB. Pending terms exist only in the active workflow state and surface in the human review UI alongside newly discovered terms.

> **Known limitation (phase 1):** Rejected terms are not persisted. If the same term appears in a later chapter, it will be proposed again. A rejection suppression store is a phase 2 improvement.

### Read-through caching

The glossary is loaded from the database exactly once — at glossary extraction time — into the state object. All downstream agents (translator, editor) read from state only. This avoids redundant DB calls in the hot path and keeps agent nodes stateless with respect to persistence.

---

## Database Schema

**Technology:** PostgreSQL (Docker Compose locally; AWS RDS in future phases)

### `glossary` table

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `novel_name` | VARCHAR | Scopes terms per novel. Phase 2: foreign key to `novels` table |
| `chinese` | VARCHAR | Original Chinese term |
| `english` | VARCHAR | Approved English translation |
| `description` | TEXT | Brief context note (optional) |
| `translated_at_chapter` | INT | Chapter number where term was first approved |
| `status` | VARCHAR | `pending_review` or `approved` only — enforced by CHECK constraint |
| `created_at` | TIMESTAMP | UTC |
| `updated_at` | TIMESTAMP | UTC |

> **Known limitation (phase 1):** `novel_name` is a plain string. A `novels` table with a `novel_id` foreign key is a phase 2 improvement.

---

## Data Access Map

Every database and S3 interaction, mapped to the node that performs it.

| Node | Store | Operation | Detail |
|---|---|---|---|
| S3 retrieval | S3 | READ | Fetch raw Chinese text for chapter N |
| Glossary extractor | PostgreSQL | READ | Load approved terms for this novel |
| Glossary DB write | PostgreSQL | CREATE | Bulk insert newly approved terms |
| Translator | — | none | Reads glossary from state only |
| Editor | — | none | Reads translated text and rules from state only |
| HITL: final review | — | none | Human decision written to state via API |
| Complete node | S3 | CREATE | Write `final_text` as `.md` file |

---

## S3 Storage

S3 access is handled by a Python storage module (`storage/s3_chapters.py`) that exposes two operations:

- `fetch_chapter(novel_name: str, chapter_number: int) → str`
- `upload_chapter(novel_name: str, chapter_number: int, content: str) → None`

**These operations are called programmatically by the LangGraph nodes, not by the LLM.** The node always knows the exact S3 key from state — there is no decision for the LLM to make. Keeping S3 as a normal storage integration avoids unnecessary protocol and process overhead.

Chapter numbers are zero-padded to three digits in S3 keys (`chapter-001`, not `chapter-1`).

### S3 bucket structure

```
s3://wuxia-translation/
  raw/
    <novel-name>/
      chapter-001.txt
      chapter-002.txt
  translated/
    <novel-name>/
      chapter-001.md
      chapter-002.md
```

All `raw/` reads are performed by the S3 retrieval node.
All `translated/` writes are performed by the complete node.
`raw/` is read-only from the storage module's perspective — `upload_chapter` must only write to `translated/`.
Overwriting an existing translated chapter raises an exception (phase 1 is create-only).

---

## Editor Agent — Formatting Rules

The editor agent enforces formatting standards via its system prompt. Rules are stored in `backend/prompts/editor.txt` — edit that file to change them without touching application code.

Phase 1 rules:

- Thoughts and internal monologue must be italicised
- Em dashes are not permitted — use commas or restructure the sentence
- Dialogue must be wrapped in double quotation marks
- Chapter breaks use `---` horizontal rule

> **Phase 2 improvement:** Formatting rules stored in a `formatting_rules` DB table, loaded into editor prompt at runtime. Allows per-novel rule customisation without file changes.

---

## API Layer

**Framework:** FastAPI (Python)

### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/workflow/start` | Start a new workflow. Returns `{workflow_id}`. |
| `GET` | `/api/workflow/{id}/status` | Poll workflow status and payload. |
| `POST` | `/api/review/glossary` | Submit glossary term decisions. Resumes graph. |
| `POST` | `/api/review/final` | Approve translation or request revision. Resumes graph. |

### Status endpoint response shape

```json
{
  "status": "glossary_review",
  "error_detail": null,
  "glossary_terms": [...],
  "edited_text": null
}
```

`glossary_terms` is non-null only when `status="glossary_review"`.
`edited_text` is non-null only when `status="final_review"`.
`error_detail` is non-null only when `status="error"`.

The full `WorkflowState` object is never exposed via the API. Only these four fields are returned.

### CORS

Allowed origin: `http://localhost:3000` (Next.js dev server). Wildcard `*` is not permitted.

---

## Frontend

**Framework:** Next.js (App Router)

The UI is a single-page application. There is no routing — the active panel is driven by the `status` field returned by the polling hook.

### Panels by status

| Status | Panel rendered |
|---|---|
| (no workflow) | `StartPanel` — novel name + chapter number form |
| `fetching` `translating` `editing` | `LoadingPanel` — spinner |
| `glossary_review` | `GlossaryReview` — term approval table |
| `final_review` | `FinalReview` — prose display + approve/revise |
| `complete` | `CompletePanel` — final text + reset |
| `error` | `ErrorBanner` — error_detail + start over |

### Polling

`useWorkflow` hook polls `GET /api/workflow/{id}/status` every 2 seconds. Polling stops automatically when status is `complete` or `error`. The hook cleans up its interval on unmount.

`workflow_id` is stored in React state only — not in `localStorage`. A page refresh resets the app to `StartPanel`. This is intentional for phase 1.

---

## Tech Stack Summary

| Layer | Technology |
|---|---|
| Orchestration | LangGraph |
| LLM | Anthropic Claude (`claude-sonnet-4-20250514`) |
| S3 integration | boto3 storage module |
| Database | PostgreSQL (Docker locally) |
| API layer | FastAPI (Python) |
| Frontend | Next.js (App Router) |
| Containerisation | Docker Compose |
| Cloud deployment | AWS ECS (phase 2) |

---

## Improvements 

- Resumable workflows across server restarts (LangGraph Postgres checkpointer)
- Per-node model selection (e.g. cheaper model for editor, stronger for translator)
- `novels` table with foreign key relationship to glossary
- `rejected` status column to suppress re-proposal of rejected terms
- Formatting rules stored in DB, configurable per novel
- Translation update workflow (currently create-only)
- Glossary term versioning (track changes to approved translations over time)
- AWS ECS deployment
