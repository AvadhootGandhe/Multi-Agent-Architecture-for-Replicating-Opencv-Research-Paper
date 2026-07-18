# Research Paper Replicator

A production-oriented scaffold for a multi-agent Computer Vision research paper implementation replication platform.

The platform accepts a research paper PDF, parses it into structured knowledge artifacts, plans an implementation, generates a runnable project scaffold, validates it, evaluates the generated implementation against the parsed knowledge, and prepares the output for human review.

## Scope

This system recreates software implementation structure only.

It does not download datasets, train models, tune hyperparameters, reproduce benchmark results, or claim scientific reproduction.

## Architecture

```text
User
  -> Frontend upload/review console
  -> FastAPI backend
  -> Parser agent
  -> Versioned knowledge repository
  -> Planner agent
  -> Builder agent
  -> Testing agent
  -> Evaluator agent
  -> Human review
  -> Downloadable generated project
```

The parser is the only component that reads the uploaded PDF. Downstream agents communicate through typed Pydantic models and generated JSON artifacts.

## Repository Layout

```text
backend/
  app/
    agents/
    api/
    core/
    domain/
    orchestrator/
    services/
  tests/
frontend/
  app/
  components/
  lib/
  types/
docker-compose.yml
```

## Local Development

Backend:

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Optional LiteLLM-backed agents:

```bash
pip install -r requirements-llm.txt
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` and upload a PDF.

## Docker

```bash
docker compose up --build
```

Services:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000/api`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`
- Qdrant: optional profile with `docker compose --profile memory up`

## Generated Artifacts

Each run writes to `backend/generated/<run-id>/`:

- `input/paper.pdf`
- `knowledge/*.json`
- `project/`
- `checkpoints/*.json`
- `archives/replicated-project.zip`

## Current Implementation

The backend includes deterministic agents so the platform works without external LLM credentials. The architecture includes an optional LiteLLM adapter and is ready for LangGraph checkpoint persistence; the current workflow keeps a local fallback so tests and development remain reliable.

## Validation

```bash
cd backend
pytest
```

```bash
cd frontend
npm run typecheck
npm run build
```
