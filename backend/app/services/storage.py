from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.domain.schemas import (
    AgentLog,
    AgentName,
    KnowledgeBundle,
    ReplicationState,
    RunSnapshot,
    RunStatus,
)


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        return self.root / run_id

    def create_run(self, run_id: str) -> Path:
        run_dir = self.run_dir(run_id)
        for child in ["input", "knowledge", "project", "checkpoints", "reports", "archives"]:
            (run_dir / child).mkdir(parents=True, exist_ok=True)
        return run_dir

    def initialize_snapshot(self, run_id: str, filename: str) -> RunSnapshot:
        now = datetime.now(UTC)
        state = ReplicationState(run_id=run_id, status=RunStatus.queued)
        snapshot = RunSnapshot(
            run_id=run_id,
            filename=filename,
            status=RunStatus.queued,
            created_at=now,
            updated_at=now,
            state=state,
        )
        self.save_snapshot(snapshot)
        return snapshot

    def load_snapshot(self, run_id: str) -> RunSnapshot:
        path = self.run_dir(run_id) / "snapshot.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return RunSnapshot.model_validate(data)

    def save_snapshot(self, snapshot: RunSnapshot) -> None:
        snapshot.updated_at = datetime.now(UTC)
        snapshot.status = snapshot.state.status
        path = self.run_dir(snapshot.run_id) / "snapshot.json"
        path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")

    def checkpoint(self, snapshot: RunSnapshot, label: str) -> None:
        path = self.run_dir(snapshot.run_id) / "checkpoints" / f"{snapshot.state.iteration:02d}-{label}.json"
        path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")

    def log(self, snapshot: RunSnapshot, agent: AgentName, message: str, payload: dict[str, Any] | None = None, level: str = "info") -> None:
        snapshot.state.logs.append(AgentLog(agent=agent, message=message, payload=payload or {}, level=level))
        self.save_snapshot(snapshot)

    def save_knowledge(self, run_id: str, bundle: KnowledgeBundle) -> None:
        knowledge_dir = self.run_dir(run_id) / "knowledge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        files = {
            "paper.json": bundle.paper.model_dump(),
            "architecture.json": {"architecture": bundle.paper.architecture, "backbone": bundle.paper.backbone},
            "implementation.json": {
                "libraries": bundle.paper.external_libraries,
                "dependencies": bundle.paper.dependencies,
                "notes": bundle.paper.implementation_notes,
            },
            "equations.json": {"equations": bundle.paper.equations, "loss_functions": bundle.paper.loss_functions},
            "pipeline.json": {
                "pipeline": bundle.paper.pipeline,
                "preprocessing": bundle.paper.preprocessing,
                "postprocessing": bundle.paper.postprocessing,
                "inference": bundle.paper.inference_pipeline,
            },
            "modules.json": {"methodology": bundle.paper.methodology, "algorithms": bundle.paper.algorithms},
            "figures.json": {"figures": bundle.paper.figures},
            "tables.json": {"tables": bundle.paper.tables},
            "notes.json": {"appendix": bundle.paper.appendix, "pseudocode": bundle.paper.pseudocode},
        }
        for filename, payload in files.items():
            (knowledge_dir / filename).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def append_human_feedback(self, run_id: str, message: str) -> None:
        snapshot = self.load_snapshot(run_id)
        if message.strip():
            snapshot.state.human_feedback.append(message.strip())
            snapshot.state.status = RunStatus.planning
            self.log(snapshot, AgentName.orchestrator, "Human feedback accepted.", {"message": message.strip()})
        self.save_snapshot(snapshot)

    def archive_project(self, run_id: str) -> Path:
        run_dir = self.run_dir(run_id)
        project_dir = run_dir / "project"
        archive_base = run_dir / "archives" / "replicated-project"
        archive_path = archive_base.with_suffix(".zip")
        if archive_path.exists():
            archive_path.unlink()
        shutil.make_archive(str(archive_base), "zip", project_dir)
        return archive_path
