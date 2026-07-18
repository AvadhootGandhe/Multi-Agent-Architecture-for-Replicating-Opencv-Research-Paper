from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    queued = "queued"
    parsing = "parsing"
    planning = "planning"
    building = "building"
    testing = "testing"
    evaluating = "evaluating"
    human_review = "human_review"
    completed = "completed"
    failed = "failed"


class AgentName(str, Enum):
    parser = "parser"
    planner = "planner"
    builder = "builder"
    tester = "tester"
    evaluator = "evaluator"
    orchestrator = "orchestrator"


class AgentLog(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent: AgentName
    level: Literal["info", "warning", "error"] = "info"
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class PaperMetadata(BaseModel):
    title: str = "Untitled Computer Vision Paper"
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    source_filename: str = ""
    page_count: int = 0


class PaperKnowledge(BaseModel):
    metadata: PaperMetadata
    problem_statement: str = ""
    contributions: list[str] = Field(default_factory=list)
    methodology: list[str] = Field(default_factory=list)
    architecture: list[str] = Field(default_factory=list)
    pipeline: list[str] = Field(default_factory=list)
    algorithms: list[str] = Field(default_factory=list)
    equations: list[str] = Field(default_factory=list)
    figures: list[str] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)
    backbone: str | None = None
    loss_functions: list[str] = Field(default_factory=list)
    training_procedure: list[str] = Field(default_factory=list)
    hyperparameters: dict[str, str] = Field(default_factory=dict)
    implementation_notes: list[str] = Field(default_factory=list)
    preprocessing: list[str] = Field(default_factory=list)
    postprocessing: list[str] = Field(default_factory=list)
    inference_pipeline: list[str] = Field(default_factory=list)
    external_libraries: list[str] = Field(default_factory=lambda: ["torch", "torchvision", "opencv-python"])
    dependencies: list[str] = Field(default_factory=list)
    folder_structure: list[str] = Field(default_factory=list)
    pseudocode: list[str] = Field(default_factory=list)
    appendix: list[str] = Field(default_factory=list)
    raw_text: str = ""


class KnowledgeBundle(BaseModel):
    paper: PaperKnowledge
    artifacts: dict[str, Any] = Field(default_factory=dict)
    version: int = 1


class PlanTask(BaseModel):
    id: str
    title: str
    description: str
    dependencies: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class ImplementationPlan(BaseModel):
    summary: str
    tasks: list[PlanTask]
    dependency_graph: dict[str, list[str]] = Field(default_factory=dict)
    revision: int = 1
    # What the planner was told to address (from evaluator or human)
    addressing_feedback: list[str] = Field(default_factory=list)


class BuildArtifact(BaseModel):
    path: str
    kind: Literal["source", "config", "test", "documentation", "container"]
    description: str


class BuildResult(BaseModel):
    project_root: Path
    artifacts: list[BuildArtifact]
    notes: list[str] = Field(default_factory=list)


class TestDiagnostics(BaseModel):
    passed: bool
    checks: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    # Structured errors per file for builder to fix
    file_errors: dict[str, list[str]] = Field(default_factory=dict)


class EvaluationReport(BaseModel):
    overall_match: float = Field(ge=0, le=100)
    missing: list[str] = Field(default_factory=list)
    extra: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    complete: bool = False
    # Structured feedback for the planner on what to address next
    planner_feedback: list[str] = Field(default_factory=list)


class ReplicationState(BaseModel):
    run_id: str
    status: RunStatus = RunStatus.queued
    iteration: int = 0
    build_attempt: int = 0
    knowledge: KnowledgeBundle | None = None
    plan: ImplementationPlan | None = None
    build: BuildResult | None = None
    diagnostics: TestDiagnostics | None = None
    evaluation: EvaluationReport | None = None
    logs: list[AgentLog] = Field(default_factory=list)
    # Human feedback — re-enters at planner
    human_feedback: list[str] = Field(default_factory=list)
    # Accumulated planner feedback from evaluator across iterations
    evaluation_feedback: list[str] = Field(default_factory=list)
    # Current build-cycle test errors passed to builder for repair
    build_errors: list[str] = Field(default_factory=list)


class RunSnapshot(BaseModel):
    run_id: str
    filename: str
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    state: ReplicationState


class RunCreateResponse(BaseModel):
    run_id: str
    status: RunStatus
    detail: str
