# AI Novel Translation

An AI-assisted Chinese-to-English novel translation workflow with explicit human review at the decisions that matter.

Rather than sending a chapter through a single prompt, the application coordinates glossary extraction, terminology approval, translation, editorial revision, manual editing, and create-only storage through a LangGraph state machine.

FastAPI starts and controls an asynchronous LangGraph workflow
Next.js presents chapter selection and human review checkpoints
PostgreSQL stores approved terminology; S3 stores source and approved translated chapters.

![Final translation review](docs/screenshots/final-review.png)

## Why This Project

Long-form fiction translation needs more than fluent output. Character names, cultivation terms, titles, and recurring concepts must remain consistent across chapters, while an editor still needs control over the final prose.

This project demonstrates how to combine LLM automation with human judgment:

- Extract chapter-specific terminology and reuse previously approved translations.
- Pause the workflow for reviewers to approve, edit, reject, or add glossary terms.
- Translate with an approved, novel-scoped glossary.
- Validate editorial formatting and surface non-blocking quality warnings.
- Let reviewers request another AI revision or manually edit the final text.
- Save approved translations without silently overwriting existing work.

## Workflow

![Compiled LangGraph translation workflow](graph_output.png)

This visualization is generated from the compiled LangGraph workflow in
`backend/src/novel_translation_backend/graph/graph.py`. Solid edges are direct
transitions; dotted edges are conditional routes that skip glossary review,
request another editor pass, or advance to completion.

| Glossary review | Translation complete |
|---|---|
| ![Glossary review](docs/screenshots/glossary-review.png) | ![Completed workflow](docs/screenshots/complete.png) |

## Features

### Human in the loop interrupts

The translation lifecycle is an explicit LangGraph graph with two human-in-the-loop interrupts. Each node has a narrow responsibility, and a typed state object makes the data passed between stages inspectable.

### Terminology consistency

Glossary terms are scoped by novel and persisted in PostgreSQL after approval. The translator receives approved matches through workflow state, while missing approved terms are surfaced as review warnings.

### Controlled editorial loop

The editor validates its output and retries corrections finite times before returning a warning. At final review, a human can request another AI editing pass with feedback or switch to manual editing before approval.

### Defensive final saves

Approved chapters are written to S3 with create-only semantics. An identical existing translation is treated as an idempotent success; different existing content produces a conflict instead of being overwritten. Temporary save failures preserve the final text and can be retried from the UI.
Active workflows and LangGraph checkpoints live in memory. This keeps the local architecture straightforward, but restarting the backend loses in-flight work. Persistent checkpointing is intentionally left as a future  improvement.

## Tech Stack

| Layer | Technology |
|---|---|
| Workflow orchestration | LangGraph |
| LLM integration | OpenAI Responses API |
| Models | `gpt-5.4-nano` for extraction/editing, `gpt-5.4-mini` for translation |
| API | FastAPI |
| Frontend | Next.js 16, React 19 |
| Database | PostgreSQL, SQLAlchemy, Alembic |
| Object storage | Amazon S3 via boto3 |
| Local environment | Docker Compose |

## Local Setup

### Prerequisites

- Docker with Docker Compose
- OpenAI API key
- AWS credentials with read/write access to an S3 bucket

### 1. Configure the environment

```bash
cp .env.example .env
```

Fill in the required values:

```env
OPENAI_API_KEY=...
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/novel_translation
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=...
S3_BUCKET_NAME=...
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=novel_translation
```

### 2. Start the services and migrate the database

```bash
docker compose up --build
docker compose exec backend alembic upgrade head
```

| Service | URL |
|---|---|
| Review workspace | [http://localhost:5173](http://localhost:5173) |
| FastAPI documentation | [http://localhost:8000/docs](http://localhost:8000/docs) |
| PostgreSQL | `localhost:5432` |

### 3. Add source chapters

The S3 catalog is built from raw chapter objects. Chapter numbers use at least four digits and both source and translated objects are plain-text files.

```text
s3://<bucket>/
├── raw/
│   └── <novel-name>/
│       └── chapter-0001.txt
└── translated/
    └── <novel-name>/
        └── chapter-0001.txt
```

Open the review workspace, select an untranslated chapter, and start the workflow.

## Project Structure

```text
.
├── backend/
│   ├── src/novel_translation_backend/
│   │   ├── api/          # FastAPI routes and configuration
│   │   ├── db/           # Glossary persistence
│   │   ├── graph/        # LangGraph state, runner, and nodes
│   │   ├── llm/          # Shared OpenAI client and model routing
│   │   ├── prompts/      # Versioned extraction, translation, and editor prompts
│   │   └── storage/      # S3 catalog, reads, and create-only saves
│   ├── migrations/
│   └── tests/
├── frontend/
│   ├── app/              # Next.js App Router entry points
│   └── src/              # Workflow components and polling hook
├── docs/
├── infra/
└── docker-compose.yml
```

## API Surface

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/chapters` | List source chapters and translation status |
| `GET` | `/api/chapters/{novel}/{chapter}` | Open a completed source/translation pair |
| `POST` | `/api/workflow/start` | Start a background translation workflow |
| `GET` | `/api/workflow/{id}/status` | Poll stage-specific workflow state |
| `POST` | `/api/workflow/{id}/kill` | Cancel and discard an active workflow |
| `POST` | `/api/workflow/{id}/retry-save` | Retry a temporary final-save failure |
| `POST` | `/api/review/glossary` | Submit glossary decisions and additions |
| `POST` | `/api/review/editor` | Request another AI editorial pass |
| `POST` | `/api/review/final` | Approve manually reviewed final text |

## Verification

```bash
cd backend
uv run pytest
```

Frontend behavior is currently verified manually against the workflow acceptance checklist in [`docs/ui-design.md`](docs/ui-design.md).

Regenerate the workflow visualization from the compiled graph:

```bash
cd backend
set -a
source ../.env
set +a
uv run python -c "from novel_translation_backend.graph.graph import graph; graph.get_graph().draw_mermaid_png(output_file_path='../graph_output.png')"
```

The default LangGraph PNG renderer calls `mermaid.ink`, so regeneration requires
network access.

## Architecture

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the graph lifecycle, state ownership, API contracts, persistence boundaries, failure handling, and known limitations.
