from pathlib import Path

from app.orchestrator.graph import run_replication
from app.services.storage import ArtifactStore


def test_replication_workflow_creates_project(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    store.create_run("run-1")
    store.initialize_snapshot("run-1", "paper.pdf")
    paper = tmp_path / "run-1" / "input" / "paper.pdf"
    paper.write_text("A Vision Paper\nAbstract\nEncoder decoder attention model with cross entropy.", encoding="utf-8")

    run_replication("run-1", paper, store)
    snapshot = store.load_snapshot("run-1")

    assert snapshot.state.build is not None
    assert (tmp_path / "run-1" / "project" / "README.md").exists()
    assert snapshot.state.evaluation is not None

