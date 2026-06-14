# Wuxia Translation AI

An AI-orchestrated pipeline that translates novels from Chinese to English. The system combines LLM agents, human-in-the-loop review checkpoints, a persistent glossary database, and cloud storage — coordinated by a LangGraph state machine.

---

## How it works

A user submits a chapter to translate. The pipeline runs automatically, pausing twice for human review before saving the final output to S3.

```
User submits chapter
      │
      ▼
  S3 retrieval          — fetches raw Chinese text
      │
      ▼
  Glossary extractor    — LLM identifies terms, proposes translations
      │
      ▼
  ⏸  Glossary review    — human approves / edits / rejects terms
      │
      ▼
  Glossary DB write     — persists approved terms
      │
      ▼
  Translator            — LLM translates using approved glossary
      │
      ▼
  Editor                — LLM enforces formatting rules
      │
      ▼
  ⏸  Final review       — human approves or requests revision
      │
      ▼
  Complete              — saves final translation to S3
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph |
| LLM | Anthropic Claude (`claude-sonnet-4-20250514`) |
| S3 integration | boto3 storage module |
| Database | PostgreSQL (local via Docker) |
| API | FastAPI (Python) |
| Frontend | Next.js |
| Containerisation | Docker Compose |

---


```
wuxia-translation-ai/
├── backend/
│   ├── api/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── config.py            # Settings / env var loading
│   │   └── routes/
│   │       ├── workflow.py      # POST /start, GET /status
│   │       └── review.py        # POST /review/glossary, /review/final
│   ├── graph/
│   │   ├── state.py             # WorkflowState TypedDict
│   │   ├── graph.py             # LangGraph StateGraph definition
│   │   ├── runner.py            # asyncio task runner + state_store
│   │   └── nodes/
│   │       ├── s3_retrieval.py
│   │       ├── glossary_extractor.py
│   │       ├── hitl_glossary.py
│   │       ├── glossary_db_write.py
│   │       ├── translator.py
│   │       ├── editor.py
│   │       ├── hitl_final.py
│   │       └── complete.py
│   ├── db/
│   │   └── glossary_repo.py     # DB access layer
│   ├── llm/
│   │   └── client.py            # Shared Anthropic client singleton
│   ├── storage/
│   │   └── s3_chapters.py       # S3 chapter fetch and upload operations
│   ├── migrations/
│   │   └── 001_glossary.py      # Alembic migration
│   ├── models/
│   │   └── glossary.py          # SQLAlchemy model
│   └── prompts/
│       ├── glossary_extractor.txt
│       ├── translator.txt
│       └── editor.txt
├── frontend/
│   ├── app/                     # Next.js App Router
│   │   └── page.tsx             # Single-page workflow UI
│   ├── components/
│   │   ├── StatusBar.tsx        # Pipeline stage progress bar
│   │   ├── StartPanel.tsx       # Chapter submission form
│   │   ├── GlossaryReview.tsx   # Term approval table
│   │   ├── FinalReview.tsx      # Translation approval + feedback
│   │   ├── CompletePanel.tsx    # Success + final text display
│   │   ├── LoadingPanel.tsx     # Spinner for non-interactive states
│   │   └── ErrorBanner.tsx      # Error display + reset
│   └── hooks/
│       └── useWorkflow.ts       # Polling hook for workflow status
├── infra/
│   └── (future ECS / Lambda config)
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Prerequisites

- Docker and Docker Compose
- An Anthropic API key
- AWS credentials with read/write access to your S3 bucket
- Node.js 18+ (for local frontend development outside Docker)
- Python 3.11+ (for local backend development outside Docker)

---

## Local setup

### 1. Clone and configure environment

```bash
git clone https://github.com/your-org/wuxia-translation-ai.git
cd wuxia-translation-ai
cp .env.example .env
```

Open `.env` and fill in your values:

```env
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/wuxia
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-southeast-1
S3_BUCKET_NAME=wuxia-translation
```

### 2. Start all services

```bash
docker compose up
```

This starts three services:

| Service | URL |
|---|---|
| Next.js frontend | http://localhost:3000 |
| FastAPI backend | http://localhost:8000 |
| PostgreSQL | localhost:5432 |

The backend waits for the database healthcheck before starting.

### 3. Run database migrations

In a separate terminal, once the containers are up:

```bash
docker compose exec backend alembic upgrade head
```

### 4. Open the app

Navigate to [http://localhost:3000](http://localhost:3000). Enter a novel name and chapter number to start a translation workflow.

---

## S3 bucket structure

Raw source texts and completed translations are stored in separate prefixes:

```
s3://translation/
  raw/
    <novel-name>/
      chapter-001.txt
      chapter-002.txt
  translated/
    <novel-name>/
      chapter-001.md
      chapter-002.md
```

Place your raw Chinese chapter files under `raw/<novel-name>/` before running the pipeline. The pipeline reads from `raw/` and writes to `translated/` — it will never overwrite a file in `raw/`.

---

## API reference

The FastAPI backend exposes four endpoints. Interactive docs are available at [http://localhost:8000/docs](http://localhost:8000/docs).

### `POST /api/workflow/start`

Starts a new translation workflow.

```json
// Request
{ "novel_name": "legendary-moonlight-sculptor", "chapter_number": 5 }

// Response
{ "workflow_id": "3f7a2c1e-..." }
```

### `GET /api/workflow/{workflow_id}/status`

Polls workflow status. The frontend calls this every 2 seconds.

```json
// Response (during glossary review)
{
  "status": "glossary_review",
  "glossary_terms": [...],
  "edited_text": null,
  "error_detail": null,
  "warnings": []
}

// Response (on error)
{
  "status": "error",
  "error_detail": "ChapterNotFoundError: chapter-005.txt not found in S3",
  "glossary_terms": null,
  "edited_text": null,
  "warnings": []
}
```

Possible `status` values: `pending` · `fetching` · `glossary_review` · `translating` · `editing` · `final_review` · `complete` · `error`

### `POST /api/review/glossary`

Submits human decisions on glossary terms.

```json
{
  "workflow_id": "3f7a2c1e-...",
  "decisions": [
    { "term_id": "abc", "action": "approve", "approved_english": "Sword Saint" },
    { "term_id": "def", "action": "reject" }
  ]
}
```

### `POST /api/review/final`

Approves the translation or sends it back to the editor with feedback.

```json
// Approve
{ "workflow_id": "3f7a2c1e-...", "action": "approve" }

// Request revision
{ "workflow_id": "3f7a2c1e-...", "action": "revise", "feedback": "The internal monologue in paragraph 3 reads too stiffly. Loosen it." }
```

---

## Glossary behaviour

The glossary is the source of truth for how novel-specific terms are translated consistently across chapters.

| Term status | Behaviour |
|---|---|
| `approved` | Silently loaded into the translator's context. Not shown for re-review. |
| `pending_review` | Shown to the human alongside newly discovered terms for the current chapter. |
| `rejected` | Dropped from workflow state and never written to the database. Will be re-proposed if encountered in a later chapter. |

The glossary is read from the database once per workflow at extraction time and passed through state to all downstream nodes. No node after the glossary extractor makes a database read.

> **Phase 1 known limitation:** rejected terms are not suppressed in future chapters. Glossary hygiene is managed manually. A rejection suppression mechanism is planned for phase 2.

---

## Editor formatting rules

The editor agent enforces these rules on every translation. They are defined in `backend/prompts/editor.txt` — edit that file to change them without touching any code.

- Internal monologue and thoughts are italicised
- Em dashes are not permitted — use commas or restructure the sentence
- All dialogue is wrapped in double quotation marks
- Internal monologue is italicised
- Existing chapter headings use `Chapter <number>: <title>`
- Scene changes use `***`
- Hyphens and em dashes are not permitted
- Chapter breaks use `---` horizontal rule

---

## Development

### Running backend only (without Docker)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

### Running frontend only (without Docker)

```bash
cd frontend
npm install
npm run dev
```

The Next.js dev server runs on port 3000 and proxies API requests to `http://localhost:8000`.

### Database migrations

```bash
# Create a new migration
cd backend && alembic revision --autogenerate -m "description"

# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1
```

---

## Architecture decisions

**Why LangGraph?** Human-in-the-loop interrupts are a first-class primitive (`interrupt()` / `resume()`), not bolted on. The workflow is an explicit directed graph — every node and edge is visible in code. State is a single typed dict, making data flow auditable.

**Why is S3 called programmatically rather than via LLM tool use?** Fetching and uploading chapters is deterministic infrastructure work. The node always knows exactly which S3 key to use from state. Letting the LLM invoke the tool adds latency, token cost, and a failure surface with no benefit.

**Why is the glossary cached in state?** The glossary is loaded from the database once at extraction time and passed through state to all downstream nodes. This avoids redundant DB calls in the hot path and keeps agent nodes stateless with respect to persistence.

**Why are LangGraph and FastAPI in the same process?** For simplicity, LangGraph runs as an `asyncio.create_task` inside FastAPI, with workflow state held in a module-level dict. This is intentionally simple — a proper persistence backend (LangGraph's Postgres checkpointer) and process separation are phase 2 work.

---

## Improvements

- Resumable workflows across server restarts (LangGraph Postgres checkpointer)
- Per-node model selection (cheaper model for editor, stronger for translator)
- `novels` table with foreign key relationship to glossary
- Rejection suppression — prevent re-proposal of rejected terms in future chapters
- Formatting rules stored in DB, configurable per novel without code changes
- Translation update workflow (currently create-only — overwrites are blocked)
- Glossary term versioning — track changes to approved translations over time
- AWS ECS deployment

---
