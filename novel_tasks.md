# AI Novel Translation  — Phase 1 Task Specification

> **22 tasks · 5 epics · Definition of done + guardrails per task**
> Mark a task complete by changing `[ ]` to `[x]` once all DoD items are verified.
Do not write unit tests for your changes for now 
---

## E1 — Infrastructure & project setup

---

### E1-T1 · Monorepo scaffold `critical`

- [X] Task complete

**Description**
Create repo structure: `/backend` (FastAPI), `/frontend` (Next), `/infra` (Docker). Add `.env.example`, `.gitignore`, `README`. Establish import conventions.

**Files:** `pyproject.toml` · `package.json` · `docker-compose.yml`

**Definition of done**
- [X] Running `ls` at repo root shows exactly: `backend/`, `frontend/`, `infra/`, `docker-compose.yml`, `.env.example`, `.gitignore`, `README.md`
- [X] `cd frontend && npm install && npm run build` exits 0
- [X] `.env.example` contains entries for: `ANTHROPIC_API_KEY`, `DATABASE_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME`

**Agent guardrails**
- Do not create any application logic files — scaffold only. No nodes, routes, or components yet
- Do not pin dependency versions unless explicitly told to. Use latest stable
- Do not create a `.env` file — only `.env.example` with placeholder values
- Stop and surface any ambiguity about folder naming before creating files

---

### E1-T2 · PostgreSQL schema migration `critical`

- [X] Task complete

**Dependencies:** E1-T1

**Description**
Write Alembic migration for the glossary table. Columns: `id` (UUID PK), `novel_name`, `chinese`, `english`, `description`, `translated_at_chapter`, `status`, `created_at`, `updated_at`. Seed with one test row.

**Files:** `migrations/001_glossary.py` · `models/glossary.py`

**Definition of done**
- [X] `alembic upgrade head` runs without error against a fresh local postgres instance
- [X] `SELECT * FROM glossary` returns exactly one seed row with `status='approved'`
- [X] Running migration twice (idempotency check) does not error
- [X] SQLAlchemy model in `models/glossary.py` maps 1-to-1 with migration columns — no missing or extra fields

**Agent guardrails**
- Do not add any columns not in the spec. No soft-delete, no versioning columns — those are phase 2
- `novel_name` must be `VARCHAR`, not a foreign key — the `novels` table does not exist yet
- `status` column must only permit `'pending_review'` or `'approved'` — enforce with a `CHECK` constraint
- Do not use ORM to create the table — use an explicit Alembic migration so schema is auditable

---

### E1-T3 · S3 chapter storage wrapper `critical`

- [X] Task complete

**Dependencies:** E1-T1

**Description**
Python storage module exposing `fetch_chapter(novel_name, chapter_number) → str` and `upload_chapter(novel_name, chapter_number, content) → None`. Uses boto3. Follows the `s3://novel-translation/raw/` and `/translated/` key conventions.

**Files:** `backend/src/novel_translation_backend/storage/s3_chapters.py`

**Definition of done** (User tests not agent)
- [X] `fetch_chapter('test-novel', 1)` returns a non-empty string when the object exists in S3
- [X] `upload_chapter('test-novel', 1, 'content')` creates an object at `translated/test-novel/chapter-001.md`
- [X] `fetch_chapter` raises a clear exception (not a silent `None`) when the chapter does not exist
- [X] Importing the storage module succeeds without starting a separate process
- [X] Chapter number is zero-padded to three digits in the S3 key (`chapter-001`, not `chapter-1`)

**Agent guardrails**
- Do not add any operations beyond `fetch_chapter` and `upload_chapter` — no list, no delete
- The storage functions are called programmatically by the LangGraph node, not by the LLM
- Do not hardcode AWS credentials — read from environment variables only
- `raw/` objects are read-only from the storage module's perspective — `upload_chapter` must write only to `translated/`

---

### E1-T4 · Docker Compose local dev setup `high`

- [X] Task complete

**Dependencies:** E1-T1

**Description**
Compose file with three services: `postgres`, `backend` (FastAPI hot reload), `frontend` (Vite dev server). Backend waits for postgres healthcheck.

**Files:** `docker-compose.yml` · `.env.example`

**Definition of done**
- [ ] `docker compose up` starts all three services without error
- [ ] FastAPI is reachable at `http://localhost:8000/docs`
- [ ] Next dev server is reachable at `http://localhost:5173`
- [ ] Editing a backend `.py` file triggers a reload without restarting the container
- [ ] Backend does not start until postgres healthcheck passes (check docker compose logs ordering)

**Agent guardrails**
- Do not expose postgres on a public interface — localhost only
- Do not bake secrets into the Compose file — use `env_file: .env`
- Do not add prod-mode containers, nginx, or SSL — this is local dev only
- Frontend and backend must be on the same Docker network so API calls work without CORS hacks

---

## E2 — LangGraph state machine

---

### E2-T1 · State TypedDict definition `critical`

- [X] Task complete

**Dependencies:** E1-T1

**Description**
Define `WorkflowState` TypedDict with all 14 specced fields plus `error_detail: Optional[str] = None` added for runner error capture.

**Files:** `graph/state.py`

**Definition of done**
- [X] Importing `WorkflowState` from `graph/state.py` succeeds with no missing dependencies
- [X] All 14 fields present: `workflow_id`, `novel_name`, `chapter_number`, `status`, `raw_chinese_text`, `glossary_terms`, `translated_text`, `edited_text`, `final_text`, `editor_feedback`, `created_at`, `completed_at`, `model_used`, `error_detail`
- [X] `glossary_terms` is typed as `List[GlossaryTerm]` where `GlossaryTerm` is a TypedDict with: `chinese`, `proposed_english`, `approved_english`, `status`, `is_new`
- [X] A `mypy --strict` run on `state.py` produces zero errors

**Agent guardrails**
- Do not add any fields beyond the 14 listed — no caching fields, no per-node timestamps
- Do not use a dataclass or Pydantic model — LangGraph requires a plain TypedDict
- `status` field must be typed as `str`, not an `Enum` — LangGraph serialisation does not handle Enum by default
- Do not import LangGraph in this file — `state.py` must be dependency-free so it can be imported anywhere

---

### E2-T2 · FastAPI + LangGraph process coupling `critical`

- [X] Task complete

**Dependencies:** E2-T1

> **Decision resolved:** LangGraph runs as `asyncio.create_task` inside the FastAPI process. State stored in a module-level dict.

**Description**
LangGraph runs as an asyncio background task inside the FastAPI process. Module-level `state_store` dict keyed by `workflow_id`. The runner wraps the entire graph invocation in `try/except` — any unhandled exception writes `status='error'` and `error_detail=str(exc)` to state so the polling endpoint never freezes.

**Files:** `graph/runner.py` · `api/routes/workflow.py`

**Reference implementation**
```python
async def run_graph(workflow_id: str, initial_state: WorkflowState):
    try:
        await graph.ainvoke(initial_state, config={"thread_id": workflow_id})
    except Exception as exc:
        state_store[workflow_id]["status"] = "error"
        state_store[workflow_id]["error_detail"] = str(exc)
        raise
```

**Definition of done**
- [X] `POST /api/workflow/start` returns `{workflow_id}` within 200ms (graph runs in background, does not block)
- [X] `state_store[workflow_id]` is populated and readable from the status endpoint immediately after start
- [X] Deliberately raising an exception inside a node causes `status` to become `'error'` and `error_detail` to be non-null — verifiable via `GET /api/workflow/{id}/status`
- [X] Two sequential workflow starts produce two independent entries in `state_store` with different `workflow_id`s

**Agent guardrails**
- Do not use `threading.Thread` — use `asyncio.create_task` only
- Do not share mutable state between the background task and request handlers without async-safe access patterns
- `state_store` must be a module-level dict, not a class attribute — keeps it inspectable for debugging
- Do not persist state to disk or DB in this task — in-memory only for phase 1

---

### E2-T3 · Graph definition and node wiring `critical`

- [X] Task complete

**Dependencies:** E2-T1 · E2-T2

**Description**
Define the LangGraph `StateGraph`. Wire all nodes in order: `s3_retrieval → glossary_extractor → [interrupt] → glossary_db_write → translator → editor → [interrupt] → complete`. Add conditional edges for the two review loops.

**Files:** `graph/graph.py`

**Definition of done**
- [X] `graph.get_graph().nodes` returns exactly: `s3_retrieval`, `glossary_extractor`, `hitl_glossary`, `glossary_db_write`, `translator`, `editor`, `hitl_final`, `complete`
- [X] Invoking the graph with a mock state that auto-approves both HITL checkpoints runs end-to-end without error
- [X] Glossary review loop: rejecting all terms at `hitl_glossary` routes back to `glossary_extractor`, not forward
- [X] Final review loop: requesting revision at `hitl_final` routes back to `editor` with `editor_feedback` set

**Agent guardrails**
- Do not implement any node logic in this file — `graph.py` wires only. All logic lives in `nodes/`
- Do not add any nodes not in the spec
- Conditional edge logic must read only from `state.status` — no external calls in edge functions
- The graph must be compiled (`graph.compile()`) and assigned to a module-level variable so `runner.py` can import it

---

### E2-T4 · S3 retrieval node `critical`

- [X] Task complete

**Dependencies:** E1-T3 · E2-T1

**Description**
Node calls the S3 storage function programmatically (not via LLM) to fetch raw Chinese text. Sets `status='fetching'` at entry. Stores result in `state.raw_chinese_text`. Raises on missing chapter.

**Files:** `graph/nodes/s3_retrieval.py`

**Definition of done**
- [X] Node sets `state['status'] = 'fetching'` as its first line, before any I/O
- [X] `state['raw_chinese_text']` is a non-empty string after node completes successfully
- [X] Node raises a descriptive exception (e.g. `ChapterNotFoundError`) when S3 returns 404 — does not return `None` silently
- [X] `raw_chinese_text` is never mutated by any downstream node — verify it is unchanged after translator runs

**Agent guardrails**
- Do not call the Anthropic API in this node — S3 fetch is pure infrastructure
- Do not write to `state['translated_text']` or any field other than `status` and `raw_chinese_text`
- Do not catch and swallow S3 exceptions — let them propagate so the runner's `try/except` records `error_detail`
- Do not hardcode novel name or chapter number — always read from state

---

### E2-T5 · Glossary DB write node `critical`

- [ ] Task complete

**Dependencies:** E1-T2 · E2-T1

**Description**
After human review, persist only newly approved terms. Pending and rejected terms
remain in workflow state only and are dropped from the state glossary list after
review. Use one transactional bulk insert and set `translated_at_chapter` when
the approved term is inserted.

**Files:** `graph/nodes/glossary_db_write.py` · `db/glossary_repo.py`

**Definition of done**
- [ ] A newly approved term has `status='approved'` and its approved English value populated in the DB after node runs
- [ ] Pending and rejected terms are removed from `state['glossary_terms']` and are never written to the DB
- [ ] `translated_at_chapter` is set on newly approved terms to `state['chapter_number']`
- [ ] Node is idempotent: running it twice with the same state produces the same DB state

**Agent guardrails**
- Do not write pending or rejected terms to the DB
- Do not rewrite existing approved terms
- Do not call the Anthropic API in this node
- All DB writes must be wrapped in a single transaction — partial writes are not acceptable
- Limit persistence to one bulk DB call when newly approved terms exist

---

### E2-T6 · Complete node `critical`

- [ ] Task complete

**Dependencies:** E1-T2 · E1-T3 · E2-T1

**Description**
Upload `final_text` to S3 at `/translated/<novel>/<chapter>.md` via the storage module and set `completed_at`. Glossary persistence is completed by E2-T5, so this node performs no DB calls.

**Files:** `graph/nodes/complete.py`

**Definition of done**
- [ ] After node runs, S3 object at `translated/<novel>/chapter-NNN.md` exists and contains `state['final_text']`
- [ ] `state['completed_at']` is an ISO 8601 timestamp string
- [ ] `state['status']` is set to `'complete'`
- [ ] Node performs no DB calls

**Agent guardrails**
- Do not overwrite an existing translated chapter — raise if object exists
- Do not set `final_text` from `edited_text` — `final_text` must have been set by the HITL approval step
- Do not call the Anthropic API in this node
- `completed_at` must use UTC, not local time

---

### E2-T7 · HITL interrupt scaffolding `high`

- [ ] Task complete

**Dependencies:** E2-T3

**Description**
Implement both `interrupt()` call sites. Glossary review pauses after `glossary_extractor`. Final review pauses after `editor`. Each interrupt encodes the pending decision type in state.

**Files:** `graph/nodes/hitl_glossary.py` · `graph/nodes/hitl_final.py`

**Definition of done**
- [ ] Graph pauses at `hitl_glossary` when invoked — status becomes `'glossary_review'` and graph does not advance
- [ ] Calling `resume()` with a glossary decision advances the graph to `glossary_db_write`
- [ ] Graph pauses at `hitl_final` — status becomes `'final_review'` and graph does not advance
- [ ] Calling `resume()` with `action='revise'` routes back to `editor` with `editor_feedback` populated in state

**Agent guardrails**
- Do not implement any LLM calls inside HITL nodes — they are pure control-flow nodes
- Do not auto-approve terms if the human provides no input — the graph must stay paused until an explicit `resume()`
- The interrupt must happen after status is written to state, so the polling endpoint never shows a stale status
- Do not accept `resume()` payloads without validating that `workflow_id` exists in `state_store`

---

## E3 — LLM nodes & prompts

---

### E3-T1 · Glossary extractor node + prompt `critical`

- [ ] Task complete

**Dependencies:** E1-T2 · E2-T1

**Description**
LLM receives `raw_chinese_text` and the list of already-approved terms. Identifies named entities, cultivation terms, titles, and proper nouns. Proposes English translations. Does not re-propose already-approved terms. Node does post-LLM dedup and keeps new terms as `pending_review` in workflow state only.

**Files:** `graph/nodes/glossary_extractor.py` · `prompts/glossary_extractor.txt`

**Definition of done**
- [ ] Node returns at least one `glossary_term` with `is_new=True` when given a chapter containing an unapproved named entity
- [ ] Node returns zero new terms when all entities are already in the approved list
- [ ] Every new term has `status='pending_review'` and `approved_english=None` in state and is not written to the DB
- [ ] The prompt file contains explicit negative instruction: do not propose terms present in the provided approved list

**Agent guardrails**
- Do not write pending terms to the DB — E2-T5 persists them only after human approval
- Do not pass `raw_chinese_text` to the LLM without also passing the approved terms list — missing this causes re-proposals
- Do not truncate the chapter text silently — if it exceeds the context window, raise a clear error
- Prompt must specify output format (JSON array) and the node must validate the structure before inserting to DB

---

### E3-T2 · Translator node + prompt `critical`

- [ ] Task complete

**Dependencies:** E2-T1

**Description**
LLM receives `raw_chinese_text` and the approved glossary terms from state. Translates faithfully to English, using approved terms exactly as given. Output stored in `state.translated_text`.

**Files:** `graph/nodes/translator.py` · `prompts/translator.txt`

**Definition of done**
- [ ] `state['translated_text']` is a non-empty English string after the node completes
- [ ] Every approved glossary term appears in `translated_text` in its `approved_english` form (spot-check with 3 terms)
- [ ] `state['raw_chinese_text']` is unchanged after the node runs
- [ ] Node sets `state['status'] = 'translating'` as its first line

**Agent guardrails**
- Do not pass `edited_text` or `final_text` to the translator — input is `raw_chinese_text` only
- Do not apply formatting rules (italics, em dashes) in this node — that is the editor's job
- Do not silently truncate long chapters — raise if input exceeds model context limit
- Prompt must instruct the LLM not to add translator notes, commentary, or chapter headings not in the original

---

### E3-T3 · Editor node + prompt `critical`

- [ ] Task complete

**Dependencies:** E2-T1

**Description**
LLM enforces formatting rules on `translated_text`. Addresses `editor_feedback` if set. Output stored in `edited_text`. Formatting rules (hardcoded in prompt): italicise internal monologue; no em dashes; double-quote all dialogue; chapter breaks use `---`.

**Files:** `graph/nodes/editor.py` · `prompts/editor.txt`

**Definition of done**
- [ ] `edited_text` contains no em dashes (search for `—` character)
- [ ] All dialogue in `edited_text` is wrapped in double quotation marks
- [ ] Internal monologue in `edited_text` is italicised
- [ ] When `editor_feedback` is non-null, the output demonstrably addresses the notes
- [ ] Node sets `state['status'] = 'editing'` as its first line

**Agent guardrails**
- Input is `translated_text` only — do not apply formatting rules to `raw_chinese_text` or `final_text`
- Do not overwrite `state['translated_text']` — output goes to `edited_text` only
- Formatting rules must live in the prompt file, not hardcoded in Python — the prompt file is the single source of truth
- Do not invent or add plot content not in the translation — editor role is formatting only

---

### E3-T4 · Anthropic client singleton `medium`

- [ ] Task complete

**Dependencies:** E1-T1

**Description**
Shared Anthropic client configured with `claude-sonnet-4-20250514`. `model_used` written to state at init.

**Files:** `llm/client.py`

**Definition of done**
- [ ] All three LLM nodes import from `llm/client.py` — no node instantiates its own Anthropic client
- [ ] `state['model_used']` is set to `'claude-sonnet-4-20250514'` for every workflow
- [ ] `from llm.client import get_client` works from any node without circular imports

**Agent guardrails**
- Do not hardcode the API key — read from `ANTHROPIC_API_KEY` env var only
- Do not add retry logic or custom timeouts in phase 1 — use SDK defaults
- Do not create one client per node call — instantiate once at module load

---

## E4 — FastAPI layer

---

### E4-T1 · POST /api/workflow/start `critical`

- [ ] Task complete

**Dependencies:** E2-T2 · E2-T3

**Description**
Accepts `{novel_name, chapter_number}`. Generates `workflow_id` (UUID). Initialises state with defaults. Spawns LangGraph as asyncio background task stored in module-level dict. Returns `{workflow_id}`.

**Files:** `api/routes/workflow.py`

**Definition of done**
- [ ] `POST` with `{novel_name: 'test', chapter_number: 1}` returns `{workflow_id: '<uuid>'}` with HTTP 200 within 200ms
- [ ] A second `POST` immediately after creates a different `workflow_id` — no collision
- [ ] `state_store` contains the new `workflow_id` within 100ms of the response
- [ ] Sending an invalid body (missing `novel_name`) returns HTTP 422 with a validation error message

**Agent guardrails**
- Do not block the HTTP response on any LangGraph work — background task only
- Do not accept `chapter_number < 1` or non-integer values — validate with Pydantic
- Do not allow two concurrent workflows for the same novel+chapter — return 409 if one is already running
- Do not expose the full state object in the response — return only `workflow_id`

---

### E4-T2 · GET /api/workflow/{id}/status `critical`

- [ ] Task complete

**Dependencies:** E4-T1

> **Updated:** Error handling added — runner's `try/except` guarantees status always reaches a terminal state.

**Description**
Returns `state.status` and the relevant payload for the UI. Includes `error_detail` when `status='error'`. Returns 404 for unknown `workflow_id`. Never returns a frozen status.

**Files:** `api/routes/workflow.py`

**Reference implementation**
```python
@router.get("/api/workflow/{workflow_id}/status")
async def get_status(workflow_id: str):
    state = state_store.get(workflow_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {
        "status": state["status"],
        "error_detail": state.get("error_detail"),
        "glossary_terms": state.get("glossary_terms") if state["status"] == "glossary_review" else None,
        "edited_text":    state.get("edited_text")    if state["status"] == "final_review"    else None,
    }
```

**Definition of done**
- [ ] Returns HTTP 404 with `{detail: 'Workflow not found'}` for an unknown `workflow_id`
- [ ] Returns `{status: 'error', error_detail: '<message>'}` when the runner has caught an exception
- [ ] Returns `glossary_terms` array (non-null) only when `status='glossary_review'`
- [ ] Returns `edited_text` (non-null) only when `status='final_review'`
- [ ] Response time is under 50ms (pure in-memory read, no DB or LLM calls)

**Agent guardrails**
- Do not make any DB or S3 calls in this endpoint — read from `state_store` only
- Do not return the full state object — expose only: `status`, `error_detail`, `glossary_terms`, `edited_text`
- Do not return HTTP 200 with a null body if `workflow_id` is missing — must be 404
- Do not add authentication in phase 1

---

### E4-T3 · POST /api/review/glossary `critical`

- [ ] Task complete

**Dependencies:** E2-T7 · E4-T1

**Description**
Accepts `{workflow_id, decisions: [{term_id, action: approve|reject, approved_english}]}`. Writes decisions into `state.glossary_terms`. Calls `langgraph.resume()`. Returns `{ok: true}`.

**Files:** `api/routes/review.py`

**Definition of done**
- [ ] Posting a valid decision payload returns `{ok: true}` with HTTP 200
- [ ] `state['glossary_terms']` reflects the human decisions immediately after the call
- [ ] The LangGraph graph advances past `hitl_glossary` after `resume()` is called
- [ ] Posting with a non-existent `workflow_id` returns HTTP 404
- [ ] Posting with `action='approve'` but no `approved_english` returns HTTP 422

**Agent guardrails**
- Do not allow partial payloads — all terms in state must have a decision before `resume()` is called
- Do not call `resume()` before writing decisions to state — order matters
- Do not accept any action values other than `'approve'` or `'reject'`
- Do not resume a workflow that is not currently paused at `hitl_glossary` — return 409

---

### E4-T4 · POST /api/review/final `critical`

- [ ] Task complete

**Dependencies:** E2-T7 · E4-T1

**Description**
Accepts `{workflow_id, action: approve|revise, feedback?: str}`. If `revise`, writes `feedback` into `state.editor_feedback`. Calls `langgraph.resume()`. Returns `{ok: true}`.

**Files:** `api/routes/review.py`

**Definition of done**
- [ ] `action='approve'` advances graph to `complete` node
- [ ] `action='revise'` with feedback text sets `state['editor_feedback']` and routes back to `editor`
- [ ] `action='revise'` without feedback text returns HTTP 422
- [ ] Posting with a non-existent `workflow_id` returns HTTP 404

**Agent guardrails**
- Do not accept action values other than `'approve'` or `'revise'`
- Do not resume a workflow not paused at `hitl_final` — return 409
- `feedback` is required when `action='revise'` — enforce at the Pydantic layer, not application logic
- Do not clear `editor_feedback` after the editor node runs — leave it for debugging

---

### E4-T5 · CORS, error handling, env config `medium`

- [ ] Task complete

**Dependencies:** E4-T1

**Description**
CORS middleware allowing the Vite dev origin. Global exception handler returning `{error, detail}` JSON. Settings class loading all env vars on startup.

**Files:** `api/main.py` · `api/config.py`

**Definition of done**
- [ ] A preflight `OPTIONS` request from `http://localhost:5173` returns HTTP 200 with correct CORS headers
- [ ] An unhandled exception in any route returns `{error: 'Internal server error', detail: '<message>'}` with HTTP 500
- [ ] Settings loads all required env vars on startup and raises a clear error if any are missing
- [ ] `uvicorn api.main:app --reload` starts without error with a valid `.env`

**Agent guardrails**
- CORS origin whitelist must be exactly `['http://localhost:5173']` — do not use wildcard `'*'`
- Do not log sensitive env vars (API keys, DB passwords) at startup
- Do not add authentication middleware in phase 1
- Settings must fail fast at import time if env vars are missing — not lazily at first use

---

## E5 — Next UI

---

### E5-T1 · Workflow status bar + polling hook `critical`

- [ ] Task complete

**Dependencies:** E4-T2

> **Updated:** Polling hook now stops and surfaces `error_detail` when `status='error'`.

**Description**
Top-of-page status bar showing pipeline stages as pills. Polls `GET /api/workflow/{id}/status` every 2s. If `status='error'`, stops polling and passes `error_detail` to the error banner.

**Files:** `src/components/StatusBar.tsx` · `src/hooks/useWorkflow.ts`

**Definition of done**
- [ ] Status bar renders all 6 stages: Fetching, Glossary review, Translating, Editing, Final review, Complete
- [ ] Active stage pill is visually distinct from inactive ones
- [ ] Polling stops automatically when status is `'complete'` or `'error'`
- [ ] When `status='error'`, `error_detail` is passed as a prop to the error banner
- [ ] Hook returns `{status, payload, error}` — consuming components do not call fetch directly

**Agent guardrails**
- Do not poll faster than every 2 seconds — avoid hammering the API
- Do not store `workflow_id` in `localStorage` — keep it in Nextjs  state (page refresh resets the app, by design)
- Do not render the status bar before a `workflow_id` exists
- `useWorkflow` hook must clean up its interval on unmount — no memory leaks

---

### E5-T2 · Start workflow panel `critical`

- [ ] Task complete

**Dependencies:** E4-T1

**Description**
Input panel with novel name (text) and chapter number (number) fields. Submit calls `POST /api/workflow/start`, stores `workflow_id` in Next state, transitions UI to polling mode.

**Files:** `src/components/StartPanel.tsx`

**Definition of done**
- [ ] Submitting with valid inputs calls `POST /api/workflow/start` and stores the returned `workflow_id`
- [ ] Chapter number input rejects non-integer and negative values before submission
- [ ] Submit button is disabled while the request is in flight
- [ ] If the API returns an error (non-200), the panel shows the error message inline and does not transition

**Agent guardrails**
- Do not use an HTML `<form>` element — use `button onClick` per project convention
- Do not navigate to a new page on submit — update Nextjs state in place
- Do not clear the inputs on successful submit
- Novel name must be trimmed of whitespace before sending to the API

---

### E5-T3 · Glossary review panel `critical`

- [ ] Task complete

**Dependencies:** E4-T3 · E5-T1

**Description**
Renders `glossary_terms` as a table. Each row: Chinese term (read-only), editable English proposal, approve/reject toggle. Bulk approve button. On submit, calls `POST /api/review/glossary`.

**Files:** `src/components/GlossaryReview.tsx`

**Definition of done**
- [ ] All terms from the status payload are rendered — no terms silently dropped
- [ ] Editing the English field of an approved term updates the decision payload on submit
- [ ] Bulk approve button sets all terms to approved in one click
- [ ] Submitting with any term lacking `approved_english` is blocked with an inline error message
- [ ] After successful submit, the panel shows a loading state and does not allow resubmission

**Agent guardrails**
- Do not prefill `approved_english` with `proposed_english` automatically — the human must confirm it
- Do not submit if any term has `action='approve'` and an empty `approved_english` field
- Do not allow the user to add new terms in this panel — display only what the LLM proposed
- Chinese term must be read-only — not editable

---

### E5-T4 · Final review panel `critical`

- [ ] Task complete

**Dependencies:** E4-T4 · E5-T1

**Description**
Renders `edited_text` in a prose block. Two actions: Approve or Request revision (with feedback textarea, min 10 chars). Submits to `POST /api/review/final`.

**Files:** `src/components/FinalReview.tsx`

**Definition of done**
- [ ] `edited_text` is rendered in a readable prose block with appropriate line spacing
- [ ] Approve calls `POST /api/review/final` with `{action: 'approve'}` and transitions UI to loading
- [ ] Request revision only submits when the feedback textarea is non-empty (min 10 chars)
- [ ] Submitting empty feedback is blocked with an inline validation message
- [ ] After submission, both buttons are disabled to prevent double-submit

**Agent guardrails**
- Do not render raw HTML from `edited_text` — treat as plain text to avoid XSS
- Do not allow the user to edit `edited_text` — read-only display only
- Do not auto-submit on approve without user intent — a single click must be the trigger
- Feedback textarea must enforce a minimum of 10 characters before submission is allowed

---

### E5-T5 · Complete state panel `medium`

- [ ] Task complete

**Dependencies:** E5-T1

**Description**
Success panel showing novel name and chapter number. `final_text` in a prose block. "Start new chapter" button resets all state.

**Files:** `src/components/CompletePanel.tsx`

**Definition of done**
- [ ] Panel displays novel name and chapter number from state
- [ ] `final_text` is rendered in a readable prose block
- [ ] "Start new chapter" button resets `workflow_id` and all state, returning to the start panel
- [ ] Panel is only rendered when `status='complete'`

**Agent guardrails**
- Do not allow the user to re-submit or modify `final_text` from this panel
- Do not render raw HTML from `final_text` — plain text only
- "Start new chapter" must clear all workflow state — no stale data from the previous workflow

---

### E5-T6 · Loading and error states `low`

- [ ] Task complete

**Dependencies:** E5-T1

**Description**
Spinner shown for non-interactive statuses. Error banner renders `error_detail` when `status='error'`. Graceful handling of lost `workflow_id` on page refresh.

**Files:** `src/components/LoadingPanel.tsx` · `src/components/ErrorBanner.tsx`

**Definition of done**
- [ ] Spinner is shown for statuses: `fetching`, `translating`, `editing`
- [ ] Error banner renders `error_detail` text when `status='error'`
- [ ] Error banner includes a "Start over" button that resets state to the start panel
- [ ] If the page is refreshed (`workflow_id` lost), the start panel is shown — no broken loading state

**Agent guardrails**
- Do not show the spinner for interactive statuses (`glossary_review`, `final_review`) — those have their own panels
- Do not auto-retry on error — surface the error and let the user decide to restart
- Do not render a raw stack trace in the error banner — show `error_detail` only
- "Start over" button must fully reset state, not just hide the banner

---

*AI Novel Translation — Phase 1 · Generated from architecture spec · 22 tasks*
