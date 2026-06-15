# AI Novel Translation  — Phase 1 Task Specification

> **31 tasks · 5 epics · Definition of done + guardrails per task**
> Mark a task complete by changing `[ ]` to `[x]` once all DoD items are verified.
Frontend acceptance tests are performed manually by the user. Do not add
automated frontend tests for Phase 1.
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
- [X] `.env.example` contains entries for: `OPENAI_API_KEY`, `DATABASE_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME`

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
Python storage module exposing raw and translated chapter reads, create-only
translated chapter uploads, and `save_final_chapter(...)` for idempotent final
saves. Uses boto3. Follows the `s3://novel-translation/raw/` and `/translated/`
key conventions.

**Files:** `backend/src/novel_translation_backend/storage/s3_chapters.py`

**Definition of done** (User tests not agent)
- [X] `fetch_chapter('test-novel', 1)` returns a non-empty string when the object exists in S3
- [X] `upload_chapter('test-novel', 1, 'content')` creates an object at `translated/test-novel/chapter-001.md`
- [X] `fetch_chapter` raises a clear exception (not a silent `None`) when the chapter does not exist
- [X] Importing the storage module succeeds without starting a separate process
- [X] Chapter number is zero-padded to three digits in the S3 key (`chapter-001`, not `chapter-1`)
- [X] `save_final_chapter` treats an identical existing translation as success without writing again
- [X] `save_final_chapter` raises a conflict when an existing translation differs
- [X] Temporary storage failures raise a retryable save error

**Agent guardrails**
- Do not add write or delete operations beyond the create-only `upload_chapter`
- `save_final_chapter` must reuse `upload_chapter`; it must never overwrite an object
- Compare existing and submitted final text exactly without trimming or normalization
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
Define `WorkflowState` TypedDict with fields for workflow content, editor
revision review, completion, non-blocking warnings, and structured save-recovery
errors.

**Files:** `graph/state.py`

**Definition of done**
- [X] Importing `WorkflowState` from `graph/state.py` succeeds with no missing dependencies
- [X] All 18 fields present: `workflow_id`, `novel_name`, `chapter_number`, `status`, `raw_chinese_text`, `glossary_terms`, `translated_text`, `edited_text`, `final_text`, `editor_feedback`, `editor_revision`, `created_at`, `completed_at`, `model_used`, `error_detail`, `error_stage`, `error_code`, `warnings`
- [X] `glossary_terms` is typed as `List[GlossaryTerm]` where `GlossaryTerm` is a TypedDict with: `chinese`, `proposed_english`, `approved_english`, `status`, `is_new`
- [X] A `mypy --strict` run on `state.py` produces zero errors

**Agent guardrails**
- Do not add fields beyond those listed — no caching fields or per-node timestamps
- Do not use a dataclass or Pydantic model — LangGraph requires a plain TypedDict
- `status` field must be typed as `str`, not an `Enum` — LangGraph serialisation does not handle Enum by default
- Do not import LangGraph in this file — `state.py` must be dependency-free so it can be imported anywhere

---

### E2-T2 · FastAPI + LangGraph process coupling `critical`

- [X] Task complete

**Dependencies:** E2-T1

> **Decision resolved:** LangGraph runs as `asyncio.create_task` inside the FastAPI process. State stored in a module-level dict.

**Description**
LangGraph runs as an asyncio background task inside the FastAPI process.
Module-level `state_store` dict keyed by `workflow_id`. The runner wraps the
entire graph invocation in `try/except` — any unhandled exception writes
`status='error'` and `error_detail=str(exc)` to state so the polling endpoint
never freezes. Save failures are additionally classified with `error_stage` and
`error_code` so the UI can distinguish retryable failures from conflicts.

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
- [X] Temporary complete-stage save failures set `error_stage='complete'` and `error_code='save_failed'`
- [X] Existing-content conflicts set `error_stage='complete'` and `error_code='save_conflict'`
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
Define the LangGraph `StateGraph`. Wire all nodes in order: `s3_retrieval → glossary_extractor → [conditional glossary interrupt] → glossary_db_write → translator → editor → [interrupt] → complete`. Skip glossary HITL when extraction produces no new terms. Final review may route back to `editor` for another AI revision before the human begins manual editing and approval.

**Files:** `graph/graph.py`

**Definition of done**
- [X] `graph.get_graph().nodes` returns exactly: `s3_retrieval`, `glossary_extractor`, `hitl_glossary`, `glossary_db_write`, `translator`, `editor`, `hitl_final`, `complete`
- [X] Invoking the graph with a mock state that auto-approves both HITL checkpoints runs end-to-end without error
- [X] Glossary review is single-pass: reviewed terms advance to `glossary_db_write` without looping back to extraction
- [X] Requesting AI revision routes from `hitl_final` back to `editor`
- [X] Final approval advances from `hitl_final` to `complete`

**Agent guardrails**
- Do not implement any node logic in this file — `graph.py` wires only. All logic lives in `nodes/`
- Do not add any nodes not in the spec
- Conditional edge logic must read only from workflow state — no external calls in edge functions
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
- Do not call the OpenAI API in this node — S3 fetch is pure infrastructure
- Do not write to `state['translated_text']` or any field other than `status` and `raw_chinese_text`
- Do not catch and swallow S3 exceptions — let them propagate so the runner's `try/except` records `error_detail`
- Do not hardcode novel name or chapter number — always read from state

---

### E2-T5 · Glossary DB write node `critical`

- [X] Task complete

**Dependencies:** E1-T2 · E2-T1

**Description**
After human review, persist only newly approved terms. Pending and rejected terms
remain in workflow state only and are dropped from the state glossary list after
review. Use one transactional bulk insert and set `translated_at_chapter` when
the approved term is inserted.

**Files:** `graph/nodes/glossary_db_write.py` · `db/glossary_repo.py`

**Definition of done**
- [X] A newly approved term has `status='approved'` and its approved English value populated in the DB after node runs
- [X] Pending and rejected terms are removed from `state['glossary_terms']` and are never written to the DB
- [X] `translated_at_chapter` is set on newly approved terms to `state['chapter_number']`
- [X] Node is idempotent: running it twice with the same state produces the same DB state

**Agent guardrails**
- Do not write pending or rejected terms to the DB
- Do not rewrite existing approved terms
- Do not call the OpenAI API in this node
- All DB writes must be wrapped in a single transaction — partial writes are not acceptable
- Limit persistence to one bulk DB call when newly approved terms exist

---

### E2-T6 · Complete node `critical`

- [X] Task complete

**Dependencies:** E1-T2 · E1-T3 · E2-T1

**Description**
Set status to `saving`, save `final_text` through the storage module's idempotent
save policy, and set `completed_at`. Glossary persistence is completed by E2-T5,
so this node performs no DB calls.

**Files:** `graph/nodes/complete.py`

**Definition of done**
- [X] After node runs, S3 object at `translated/<novel>/chapter-NNN.md` exists and contains `state['final_text']`
- [X] `state['completed_at']` is an ISO 8601 timestamp string
- [X] `state['status']` is set to `'complete'`
- [X] Successful completion clears `error_detail`, `error_stage`, and `error_code`
- [X] Node performs no DB calls

**Agent guardrails**
- Do not overwrite an existing translated chapter
- Treat an identical existing translated chapter as successful completion
- Raise a save conflict when an existing translated chapter differs
- Do not set `final_text` from `edited_text` — `final_text` must have been set by the HITL approval step
- Do not call the OpenAI API in this node
- `completed_at` must use UTC, not local time

---

### E2-T7 · HITL interrupt scaffolding `high`

- [X] Task complete

**Dependencies:** E2-T3

**Description**
Implement both `interrupt()` call sites. Glossary review pauses after `glossary_extractor` only when newly extracted terms exist. Final review pauses after `editor`. Each interrupt encodes the pending decision type. Compile the graph with `InMemorySaver` and resume with `Command(update=state, resume=payload)` so API changes made to the in-memory state are included in the resumed graph.

**Files:** `graph/nodes/hitl_glossary.py` · `graph/nodes/hitl_final.py`

**Definition of done**
- [X] Graph pauses at `hitl_glossary` when new terms exist and skips it when no new terms exist
- [X] Calling `resume()` with a glossary decision advances the graph to `glossary_db_write`
- [X] Graph pauses at `hitl_final` — status becomes `'final_review'` and graph does not advance
- [X] Calling `resume()` with revision feedback routes back to `editor`
- [X] Final approval requires a non-empty API-populated `final_text`
- [X] Calling `resume()` with final approval advances to `complete`

**Agent guardrails**
- Do not implement any LLM calls inside HITL nodes — they are pure control-flow nodes
- Do not auto-approve terms if the human provides no input — the graph must stay paused until an explicit `resume()`
- The interrupt must happen after status is written to state, so the polling endpoint never shows a stale status
- Do not accept `resume()` payloads without validating that `workflow_id` exists in `state_store`

---

## E3 — LLM nodes & prompts

---

### E3-T1 · Glossary extractor node + prompt `critical`

- [X] Task complete

**Dependencies:** E1-T2 · E2-T1

**Description**
LLM receives `raw_chinese_text` and extracts every qualifying glossary term that appears in the chapter without receiving the approved glossary list. The backend validates and deduplicates the extraction, then queries approved terms for only those exact trimmed Chinese candidates. Exact approved matches use the database translation; unmatched terms remain `pending_review` in workflow state only.

**Files:** `graph/nodes/glossary_extractor.py` · `prompts/glossary_extractor.txt`

**Definition of done**
- [X] Node returns at least one `glossary_term` with `is_new=True` when given a chapter containing an unapproved named entity
- [X] Exact approved database matches are marked `approved` and are not shown for re-review
- [X] Every new term has `status='pending_review'` and `approved_english=None` in state and is not written to the DB
- [X] Database lookup is limited to trimmed exact Chinese terms extracted by the LLM

**Agent guardrails**
- Do not write pending terms to the DB — E2-T5 persists them only after human approval
- Do not pass the approved glossary list to the extractor LLM
- Do not query the entire approved glossary — query only validated extracted candidates
- Do not truncate the chapter text silently — if it exceeds the context window, raise a clear error
- Prompt must specify output format (JSON array) and the node must validate the structure before inserting to DB

---

### E3-T2 · Translator node + prompt `critical`

- [X] Task complete

**Dependencies:** E2-T1

**Description**
LLM receives `raw_chinese_text` and the approved glossary terms from state. Translates faithfully to English, using approved terms exactly as given. Output stored in `state.translated_text`.

**Files:** `graph/nodes/translator.py` · `prompts/translator.txt`

**Definition of done**
- [X] `state['translated_text']` is a non-empty English string after the node completes
- [X] Missing approved glossary translations used by the chapter produce non-blocking warnings
- [X] `state['raw_chinese_text']` is unchanged after the node runs
- [X] Node sets `state['status'] = 'translating'` as its first line

**Agent guardrails**
- Do not pass `edited_text` or `final_text` to the translator — input is `raw_chinese_text` only
- Do not apply formatting rules (italics, em dashes) in this node — that is the editor's job
- Do not silently truncate long chapters — raise if input exceeds model context limit
- Prompt must instruct the LLM not to add translator notes, commentary, or chapter headings not in the original

---

### E3-T3 · Editor node + prompt `critical`

- [X] Task complete

**Dependencies:** E2-T1

**Description**
LLM enforces formatting rules on `translated_text`. On an initial pass it edits
`translated_text`; when `editor_feedback` is present it revises the latest
`edited_text`. Output replaces `edited_text`, increments `editor_revision`, and
becomes the next draft for human review. Formatting rules in the prompt:
italicise internal monologue; no hyphens or em dashes; double-quote all
dialogue; existing chapter headings use `Chapter <number>: <title>`; scene
changes use `***`.

**Files:** `graph/nodes/editor.py` · `prompts/editor.txt`

**Definition of done**
- [X] `edited_text` contains no hyphens or em dashes
- [X] Prompt requires all dialogue to be wrapped in double quotation marks
- [X] Prompt requires internal monologue to be italicised
- [X] Human `editor_feedback` is included in revision prompts
- [X] Revision requests use the latest `edited_text`, not the original translation
- [X] Every successful editor pass increments `editor_revision`
- [X] Consumed `editor_feedback` is cleared after the editor pass
- [X] Node sets `state['status'] = 'editing'` as its first line
- [X] Exhausting formatting correction retries preserves the final editor response, adds a warning, and continues to final review

**Agent guardrails**
- Initial input is `translated_text`; revision input is the latest `edited_text`
- Do not apply formatting rules to `raw_chinese_text` or `final_text`
- Do not overwrite `state['translated_text']` — output goes to `edited_text` only
- Formatting rules must live in the prompt file, not hardcoded in Python — the prompt file is the single source of truth
- Do not invent or add plot content not in the translation — editor role is formatting only
- Do not fail the workflow solely because formatting validation retries are exhausted

---

### E3-T4 · OpenAI client singleton `medium`

- [X] Task complete

**Dependencies:** E1-T1

**Description**
Shared OpenAI Responses API client with per-node model selection:
`gpt-5.4-nano` for glossary extraction and editing, and `gpt-5.4-mini` for
translation. `model_used` records the routing at workflow initialization.

**Files:** `llm/client.py`

**Definition of done**
- [X] All three LLM nodes import from `llm/client.py` — no node instantiates its own OpenAI client
- [X] `state['model_used']` records the glossary, translator, and editor models
- [X] `from novel_translation_backend.llm.client import get_client` works without circular imports

**Agent guardrails**
- Do not hardcode the API key — read from `OPENAI_API_KEY` env var only
- Do not add retry logic or custom timeouts in phase 1 — use SDK defaults
- Do not create one client per node call — instantiate once at module load

---

## E4 — FastAPI layer

---

### E4-T1 · POST /api/workflow/start `critical`

- [X] Task complete

**Dependencies:** E2-T2 · E2-T3

**Description**
Accepts `{novel_name, chapter_number}`. Generates `workflow_id` (UUID). Initialises state with defaults. Spawns LangGraph as asyncio background task stored in module-level dict. Returns `{workflow_id}`.

**Files:** `api/routes/workflow.py`

**Definition of done**
- [X] `POST` with `{novel_name: 'test', chapter_number: 1}` returns `{workflow_id: '<uuid>'}` with HTTP 200 within 200ms
- [X] A second `POST` immediately after creates a different `workflow_id` — no collision
- [X] `state_store` contains the new `workflow_id` within 100ms of the response
- [X] Sending an invalid body (missing `novel_name`) returns HTTP 422 with a validation error message

**Agent guardrails**
- Do not block the HTTP response on any LangGraph work — background task only
- Do not accept `chapter_number < 1` or non-integer values — validate with Pydantic
- Do not allow two concurrent workflows for the same novel+chapter — return 409 if one is already running
- Do not expose the full state object in the response — return only `workflow_id`

---

### E4-T2 · GET /api/workflow/{id}/status `critical`

- [X] Task complete

**Dependencies:** E4-T1

> **Updated:** Error handling added, and the UI contract now exposes final-review
> source text, non-blocking warnings, and save-recovery details.

**Description**
Returns `state.status` and the relevant payload for the UI. Includes
`error_detail`, `error_stage`, and `error_code` when `status='error'`;
`raw_chinese_text`, `edited_text`, and `editor_revision` during final review;
preserved `final_text` only for complete-stage save errors; and non-blocking
`warnings`. Returns 404 for unknown `workflow_id`. Never returns a frozen status.

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
        "raw_chinese_text": state.get("raw_chinese_text") if state["status"] == "final_review" else None,
        "edited_text":    state.get("edited_text")    if state["status"] == "final_review"    else None,
        "editor_revision": state.get("editor_revision") if state["status"] == "final_review" else None,
        "final_text": state.get("final_text") if state["status"] == "error" and state.get("error_stage") == "complete" else None,
        "error_stage": state.get("error_stage") if state["status"] == "error" else None,
        "error_code": state.get("error_code") if state["status"] == "error" else None,
        "warnings": state.get("warnings", []),
    }
```

**Definition of done**
- [X] Returns HTTP 404 with `{detail: 'Workflow not found'}` for an unknown `workflow_id`
- [X] Returns `{status: 'error', error_detail: '<message>'}` when the runner has caught an exception
- [X] Returns `glossary_terms` array (non-null) only when `status='glossary_review'`
- [X] Returns `edited_text` (non-null) only when `status='final_review'`
- [X] Returns `raw_chinese_text` (non-null) only when `status='final_review'`
- [X] Returns `editor_revision` only when `status='final_review'`
- [X] Returns preserved `final_text` only for complete-stage save errors
- [X] Returns structured `error_stage` and `error_code` values for save recovery
- [X] Returns the current non-blocking `warnings` list
- [X] Response time is under 50ms (pure in-memory read, no DB or LLM calls)

**Agent guardrails**
- Do not make any DB or S3 calls in this endpoint — read from `state_store` only
- Do not return the full state object — expose only: `status`, `error_detail`,
  `error_stage`, `error_code`, `glossary_terms`, `raw_chinese_text`,
  `edited_text`, `editor_revision`, `final_text`, `warnings`
- Do not return HTTP 200 with a null body if `workflow_id` is missing — must be 404
- Do not add authentication in phase 1

---

### E4-T3 · POST /api/review/glossary `critical`

- [X] Task complete

**Dependencies:** E2-T7 · E4-T1

**Description**
Accepts `{workflow_id, decisions: [{term_key, action: approve|reject, approved_english}], suggestions?: [{chinese, approved_english}]}` where `term_key` is the term's unique Chinese value within the workflow. Decisions are required only for newly extracted terms. User suggestions are automatically approved. Existing approved terms remain unchanged. The graph skips glossary HITL when there are no new terms and never loops back to extraction after review.

**Files:** `api/routes/review.py`

**Definition of done**
- [X] Posting a valid decision payload returns `{ok: true}` with HTTP 200
- [X] `state['glossary_terms']` reflects the human decisions immediately after the call
- [X] The LangGraph graph advances past `hitl_glossary` after `resume()` is called
- [X] Posting with a non-existent `workflow_id` returns HTTP 404
- [X] Posting with `action='approve'` but no `approved_english` returns HTTP 422
- [X] Existing approved terms remain unchanged and require no review decision
- [X] User suggestions are automatically approved and included in persistence
- [X] A second submission after resume begins returns HTTP 409

**Agent guardrails**
- Do not allow partial payloads — all new terms in state must have a decision before resume
- Do not accept decisions for existing approved terms
- Do not resume before writing decisions and auto-approved suggestions to state
- Do not accept any action values other than `'approve'` or `'reject'`
- Do not resume a workflow that is not currently paused at `hitl_glossary` — return 409
- Do not loop back to glossary extraction after review

---

### E4-T4 · POST /api/review/final `critical`

- [X] Task complete

**Dependencies:** E2-T7 · E4-T1

**Description**
Accepts `{workflow_id, final_text}`. Validates that `final_text` is not blank
without trimming or otherwise modifying the submitted text, writes it into
workflow state, sets status to `saving`, and resumes the graph with final
approval. Returns `{ok: true}`.

**Files:** `api/routes/review.py`

**Definition of done**
- [X] A non-empty `final_text` advances the graph to `complete`
- [X] Missing or whitespace-only `final_text` returns HTTP 422
- [X] Submitted line breaks and surrounding whitespace are preserved exactly
- [X] Posting with a non-existent `workflow_id` returns HTTP 404

**Agent guardrails**
- Do not resume a workflow not paused at `hitl_final` — return 409
- Do not trim or normalize the submitted `final_text`
- Do not save directly from the API endpoint — resume the graph so `complete` owns the normal save

---

### E4-T4A · POST /api/review/editor `high`

- [X] Task complete

**Dependencies:** E2-T7 · E3-T3 · E4-T1

**Description**
Accepts `{workflow_id, feedback}` while the workflow is paused at final review.
Stores non-empty human feedback, sets status to `editing`, and resumes the graph
with `action='revise'` so the editor revises the latest `edited_text`.

**Files:** `graph/runner.py` · `api/routes/review.py`

**Definition of done**
- [X] Valid feedback returns `{ok: true}` and routes the graph back to `editor`
- [X] Feedback shorter than 10 trimmed characters returns HTTP 422
- [X] Posting with a non-existent `workflow_id` returns HTTP 404
- [X] Posting when the workflow is not paused at final review returns HTTP 409
- [X] A second revision request while editing is rejected

**Agent guardrails**
- Do not accept or modify `final_text` in this endpoint
- Do not send a manually edited draft into the AI editor
- Do not allow revision after the human has entered manual editing mode
- Do not save directly from this endpoint

---

### E4-T4B · POST /api/workflow/{id}/retry-save `high`

- [X] Task complete

**Dependencies:** E1-T3 · E2-T6 · E4-T2

**Description**
Synchronously retries only a retryable complete-stage save failure using the
preserved `state.final_text`. Reuses the shared idempotent storage save policy
and never reruns translator or editor nodes.

**Files:** `graph/runner.py` · `api/routes/workflow.py`

**Definition of done**
- [X] Retry is accepted only for `status='error'`, `error_stage='complete'`, and `error_code='save_failed'`
- [X] Retry sets status to `saving` while the request waits for storage
- [X] Successful retry returns `{ok: true}`, sets `status='complete'`, and clears error fields
- [X] A repeated temporary storage failure returns HTTP 502 and remains retryable
- [X] A different existing translated chapter returns HTTP 409 and changes `error_code` to `save_conflict`
- [X] An identical existing translated chapter is treated as success without another write
- [X] Concurrent or otherwise ineligible retries return HTTP 409

**Agent guardrails**
- Do not rerun the LangGraph translation workflow during retry
- Do not accept replacement text in the retry request; use preserved `final_text`
- Do not offer retry for `save_conflict`
- Do not overwrite an existing translated chapter

---

### E4-T5 · CORS, error handling, env config `medium`

- [X] Task complete

**Dependencies:** E4-T1

**Description**
CORS middleware allowing the Vite dev origin. Global exception handler returning `{error, detail}` JSON. Settings class loading all env vars on startup.

**Files:** `api/main.py` · `api/config.py`

**Definition of done**
- [X] A preflight `OPTIONS` request from `http://localhost:5173` returns HTTP 200 with correct CORS headers
- [X] An unhandled exception in any route returns `{error: 'Internal server error', detail: '<message>'}` with HTTP 500
- [X] Settings loads all required env vars on startup and raises a clear error if any are missing
- [X] `uvicorn api.main:app --reload` starts without error with a valid `.env`

**Agent guardrails**
- CORS origin whitelist must be exactly `['http://localhost:5173']` — do not use wildcard `'*'`
- Do not log sensitive env vars (API keys, DB passwords) at startup
- Do not add authentication middleware in phase 1
- Settings must fail fast at import time if env vars are missing — not lazily at first use

---

### E4-T6 · GET /api/chapters catalog `critical`

- [X] Task complete

**Dependencies:** E1-T3

**Description**
Returns the novels and raw chapter numbers available in S3. Each chapter includes
a `translated` boolean based on whether the corresponding translated object
exists. This endpoint is the source of truth for the start-screen dropdowns.

**Files:** `api/routes/chapters.py` · `api/main.py` · `storage/s3_chapters.py`

**Definition of done**
- [X] Returns every novel that has at least one raw chapter
- [X] Returns chapter numbers in ascending numeric order
- [X] Labels a chapter `translated: true` only when its translated object exists
- [X] Returns an empty novels list when no raw chapters exist
- [X] S3 listing failures return a clear HTTP error

**Agent guardrails**
- Read from S3 only — do not query the glossary database
- Do not return raw or translated chapter text from the catalog endpoint
- Do not infer translated status from workflow memory
- Keep S3 key parsing and listing logic in the storage module

---

### E4-T7 · GET /api/chapters/{novel_name}/{chapter_number} `critical`

- [X] Task complete

**Dependencies:** E1-T3 · E4-T6

**Description**
Returns the raw Chinese and saved English text for a translated chapter so the UI
can show a read-only side-by-side comparison.

**Files:** `api/routes/chapters.py` · `storage/s3_chapters.py`

**Definition of done**
- [X] Returns `{novel_name, chapter_number, raw_chinese_text, translated_text}`
  for a translated chapter
- [X] Returns HTTP 404 when the raw chapter does not exist
- [X] Returns HTTP 404 when the translated chapter does not exist
- [X] Treats both chapter texts as plain strings

**Agent guardrails**
- This endpoint is read-only
- Do not start or resume a workflow
- Do not return S3 credentials, bucket details, or object metadata
- Validate `chapter_number` as a positive integer

---

## E5 — Next UI

---

### E5-T1 · Workflow status bar + polling hook `critical`

- [X] Task complete

**Dependencies:** E4-T2

> **Updated:** Polling hook now stops and surfaces `error_detail` when `status='error'`.

**Description**
Persistent desktop review workspace with a compact header and top-of-page status
bar showing pipeline stages as pills. Polls `GET /api/workflow/{id}/status`
every 2s. If `status='error'`, stops polling and passes `error_detail` to the
error banner.

**Files:** `src/components/StatusBar.tsx` · `src/hooks/useWorkflow.ts`

**Definition of done**
- [X] Status bar renders all 6 stages: Fetching, Glossary review, Translating, Editing, Final review, Complete
- [X] Active stage pill is visually distinct from inactive ones
- [X] Polling stops automatically when status is `'complete'` or `'error'`
- [X] When `status='error'`, `error_detail` is passed as a prop to the error banner
- [X] Active non-blocking warnings are exposed to the current review panel
- [X] Hook returns `{status, payload, error}` — consuming components do not call fetch directly

**Agent guardrails**
- Do not poll faster than every 2 seconds — avoid hammering the API
- Do not store `workflow_id` in `localStorage` — keep it in Nextjs  state (page refresh resets the app, by design)
- Do not render the status bar before a `workflow_id` exists
- `useWorkflow` hook must clean up its interval on unmount — no memory leaks

---

### E5-T2 · Start workflow panel `critical`

- [X] Task complete

**Dependencies:** E4-T1 · E4-T6 · E4-T7

**Description**
Input panel with dependent novel and chapter dropdowns populated by the catalog
endpoint. Chapters are labeled `Translated` or `Untranslated`. An untranslated
chapter can start a workflow; a translated chapter opens the read-only chapter
view.

**Files:** `src/components/StartPanel.tsx`

**Definition of done**
- [X] Novel dropdown contains every novel returned by the catalog endpoint
- [X] Selecting a novel filters the chapter dropdown to that novel
- [X] Chapters visibly show `Translated` or `Untranslated`
- [X] Starting an untranslated chapter calls `POST /api/workflow/start` and stores the returned `workflow_id`
- [X] Selecting a translated chapter opens its read-only chapter view
- [X] Submit button is disabled while the request is in flight
- [X] If the API returns an error (non-200), the panel shows the error message inline and does not transition

**Agent guardrails**
- Do not use an HTML `<form>` element — use `button onClick` per project convention
- Do not navigate to a new page on submit — update Nextjs state in place
- Do not allow a translated chapter to start a new workflow
- Treat catalog values as the source of truth; do not hard-code novel or chapter options

---

### E5-T3 · Glossary review panel `critical`

- [X] Task complete

**Dependencies:** E4-T3 · E5-T1

**Description**
Renders `glossary_terms` as a vertical list of compact review cards. Each card
shows a read-only Chinese term, context description, editable English proposal,
and explicit approve/reject controls. The proposal is prefilled into the English
field. Includes bulk approval and an Add term action. On submit, calls
`POST /api/review/glossary`.

**Files:** `src/components/GlossaryReview.tsx`

**Definition of done**
- [X] All terms from the status payload are rendered — no terms silently dropped
- [X] Each English field is prefilled with `proposed_english`
- [X] Every extracted term requires an explicit approve or reject decision
- [X] Editing the English field of an approved term updates the decision payload on submit
- [X] Bulk approve button sets all terms to approved in one click
- [X] Added terms require Chinese and approved English values and submit as suggestions
- [X] Submitting with any term lacking `approved_english` is blocked with an inline error message
- [X] After successful submit, the panel shows a loading state and does not allow resubmission

**Agent guardrails**
- Prefill with `proposed_english`, but do not treat prefill as an approval decision
- Do not submit if any term has `action='approve'` and an empty `approved_english` field
- Extracted Chinese terms must be read-only; reviewer-added terms are entered separately

---

### E5-T4 · Final review panel `critical`

- [X] Task complete

**Dependencies:** E4-T4 · E5-T1

**Description**
Three-column final review workspace with two deliberate phases. AI review mode
shows raw Chinese and the latest `edited_text` read-only, allowing another AI
revision request or transition to manual editing. Manual editing mode initializes
a local plain-text draft from the latest `edited_text`, removes AI revision
controls, and submits the human-approved `final_text`. Non-blocking warnings
appear in an amber banner above the reader.

**Files:** `src/components/FinalReview.tsx`

**Definition of done**
- [X] `raw_chinese_text` and `edited_text` render side by side with independent scrolling
- [X] AI review mode renders `edited_text` read-only
- [X] Request AI revision submits `{workflow_id, feedback}` to `POST /api/review/editor`
- [X] Revision feedback requires at least 10 trimmed characters
- [X] A returned `editor_revision` remounts the panel with the latest AI-edited text
- [X] Start manual editing initializes an editable plain-text draft from `edited_text`
- [X] AI revision controls are unavailable after manual editing begins
- [X] Non-blocking warnings remain visible without preventing approval
- [X] Approve calls `POST /api/review/final` with `{workflow_id, final_text}` and transitions UI to loading
- [X] Blank final text is blocked with an inline validation message
- [X] The textarea and approval button are disabled during submission
- [X] API submission failure re-enables editing without resetting the local draft
- [X] `FinalReview` is keyed by `workflow_id` plus `editor_revision`; polling does not overwrite human edits

**Agent guardrails**
- Do not render raw HTML from either chapter text — treat both as plain text to avoid XSS
- Do not allow AI revision after manual editing begins
- Do not synchronize the local final-text draft from polling updates
- Do not auto-submit on approve without user intent — a single click must be the trigger
- Do not trim or normalize the human-edited text before submission

---

### E5-T5 · Complete state panel `medium`

- [X] Task complete

**Dependencies:** E4-T7 · E5-T1

**Description**
Success receipt showing novel name, chapter number, and completed pipeline state.
Provides Open translated chapter and Start next chapter actions.

**Files:** `src/components/CompletePanel.tsx`

**Definition of done**
- [X] Panel displays novel name and chapter number from state
- [X] Open translated chapter loads the read-only side-by-side chapter view
- [X] Start next chapter resets `workflow_id` and all state, returning to the start panel
- [X] Panel is only rendered when `status='complete'`

**Agent guardrails**
- Do not allow the user to re-submit or modify the completed translation
- "Start new chapter" must clear all workflow state — no stale data from the previous workflow

---

### E5-T6 · Loading and error states `low`

- [X] Task complete

**Dependencies:** E5-T1

Loading panel shown for non-interactive statuses with current stage,
explanation, and elapsed time. A persistent Cancel workflow control appears in
the workspace header whenever a `workflow_id` exists, including loading, review,
complete, and error states. Error banner renders `error_detail` when
`status='error'`. Complete-stage save errors also expose the preserved final text
read-only and provide a synchronous Retry save action only for retryable
failures. Graceful handling of lost `workflow_id` on page refresh.

**Files:** `src/components/LoadingPanel.tsx` · `src/components/ErrorBanner.tsx`

**Definition of done**
- [X] Spinner is shown for statuses: `fetching`, `translating`, `editing`, `saving`
- [X] Cancel workflow is visible whenever a `workflow_id` exists, across every workflow status
- [X] Cancel workflow requires confirmation, calls the kill endpoint, and resets the UI
- [X] Cancellation errors remain visible without replacing the active workflow panel
- [X] Error banner renders `error_detail` text when `status='error'`
- [X] Error banner includes a "Start over" button that resets state to the start panel
- [X] Complete-stage save errors display preserved `final_text` read-only
- [X] `save_failed` displays Retry save and disables controls while retrying
- [X] `save_conflict` explains the conflict and does not display Retry save
- [X] If the page is refreshed (`workflow_id` lost), the start panel is shown — no broken loading state

**Agent guardrails**
- Do not show the spinner for interactive statuses (`glossary_review`, `final_review`) — those have their own panels
- Do not allow more than one active workflow in the browser session
- Do not auto-retry on error — retry requires an explicit user click
- Do not hide Cancel workflow inside status-specific panels
- Do not allow the recovery screen to edit preserved `final_text`
- Do not display the existing conflicting S3 translation
- Do not render a raw stack trace in the error banner — show `error_detail` only
- "Start over" button must fully reset state, not just hide the banner

---

### E5-T7 · Read-only translated chapter view `medium`

- [X] Task complete

**Dependencies:** E4-T7 · E5-T2 · E5-T5

**Description**
Displays raw Chinese and saved English in equal-width, independently scrolling
panels with sticky headers. Available from translated chapter selection and the
completion receipt.

**Files:** `src/components/ReadOnlyChapter.tsx`

**Definition of done**
- [X] Both chapter texts render as plain text
- [X] Panels scroll independently
- [X] No review, edit, approval, or revision controls are present
- [X] Back to chapter selection returns to the start screen
- [X] Missing chapter content displays a clear inline error

**Agent guardrails**
- Do not allow editing or workflow actions from this view
- Do not render raw HTML
- Do not start a workflow when this view opens

---

## Frontend Manual Acceptance

The user manually verifies all E5 definitions of done. Do not add automated
frontend tests for Phase 1.

---

*AI Novel Translation — Phase 1 · Generated from architecture spec · 29 tasks*
