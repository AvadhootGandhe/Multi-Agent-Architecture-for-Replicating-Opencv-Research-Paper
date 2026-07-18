from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.domain.schemas import RunCreateResponse, RunSnapshot
from app.orchestrator.graph import run_replication
from app.services.storage import ArtifactStore

router = APIRouter()
store = ArtifactStore(settings.generated_root)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/runs", response_model=RunCreateResponse)
async def create_run(
    paper: UploadFile = File(...),
) -> RunCreateResponse:
    if paper.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")

    run_id = uuid4().hex
    run_dir = store.create_run(run_id)
    pdf_path = run_dir / "input" / "paper.pdf"

    with pdf_path.open("wb") as handle:
        shutil.copyfileobj(paper.file, handle)

    snapshot = store.initialize_snapshot(run_id, filename=paper.filename or "paper.pdf")

    # Run blocking orchestration in thread pool — keeps event loop free
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, run_replication, run_id, pdf_path, store, None)

    return RunCreateResponse(run_id=run_id, status=snapshot.status, detail="Replication started.")


@router.get("/runs/{run_id}", response_model=RunSnapshot)
def get_run(run_id: str) -> RunSnapshot:
    try:
        return store.load_snapshot(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc


@router.post("/runs/{run_id}/feedback", response_model=RunSnapshot)
async def submit_feedback(run_id: str, feedback: dict[str, str]) -> RunSnapshot:
    try:
        snapshot = store.load_snapshot(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc

    pdf_path = store.run_dir(run_id) / "input" / "paper.pdf"
    store.append_human_feedback(run_id, feedback.get("message", ""))

    # Run blocking orchestration in thread pool — keeps event loop free
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, run_replication, run_id, pdf_path, store, feedback.get("message"))

    return snapshot


@router.get("/runs/{run_id}/download")
def download_project(run_id: str) -> FileResponse:
    archive_path = store.archive_project(run_id)
    if not archive_path.exists():
        raise HTTPException(status_code=404, detail="Generated project is not available yet.")
    return FileResponse(
        path=archive_path,
        filename=f"replicated-project-{run_id}.zip",
        media_type="application/zip",
    )


