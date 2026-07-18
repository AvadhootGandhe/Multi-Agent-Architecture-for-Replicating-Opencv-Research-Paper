from __future__ import annotations

import time
from pathlib import Path

import structlog

from app.agents.builder.agent import BuilderAgent
from app.agents.evaluator.agent import EvaluatorAgent
from app.agents.parser.agent import PaperParserAgent
from app.agents.planner.agent import PlannerAgent
from app.agents.tester.agent import TestingAgent
from app.core.config import settings
from app.domain.schemas import AgentName, RunStatus
from app.services.llm import LLMClient
from app.services.storage import ArtifactStore
from app.services.venv_manager import VenvManager

log = structlog.get_logger()

# Maximum build-test retries per outer iteration (builder → tester loop)
MAX_BUILD_ATTEMPTS = 3


def build_langgraph_definition() -> object | None:
    """Optional LangGraph visualization stub — not used at runtime."""
    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return None

    graph = StateGraph(dict)
    for node in ["parse", "plan", "build", "test", "evaluate"]:
        graph.add_node(node, lambda state: state)
    graph.set_entry_point("parse")
    graph.add_edge("parse", "plan")
    graph.add_edge("plan", "build")
    graph.add_edge("build", "test")
    graph.add_edge("test", "evaluate")
    graph.add_edge("evaluate", END)
    return graph.compile()


def run_replication(
    run_id: str,
    pdf_path: Path,
    store: ArtifactStore,
    feedback: str | None = None,
) -> None:
    """
    Main multi-agent orchestration loop.

    Flow:
    ┌──────────────────────────────────────────────────────────────┐
    │ Parse PDF → KnowledgeBundle (once, cached in snapshot)       │
    │                                                              │
    │ OUTER LOOP (up to MAX_ITERATIONS):                           │
    │   Planner(knowledge + eval_feedback + human_feedback) → Plan │
    │                                                              │
    │   INNER LOOP (up to MAX_BUILD_ATTEMPTS):                     │
    │     Builder(plan + prev_test_errors) → Code                  │
    │     Tester(code) → pass/fail + per-file errors               │
    │     if pass: break inner loop                                │
    │     else: pass errors to next Builder call                   │
    │                                                              │
    │   Evaluator(code + knowledge) → score 0-100                  │
    │   if score >= 90 AND tests pass → SUCCESS                    │
    │   else → planner_feedback → next outer iteration             │
    │                                                              │
    │ Exhausted → human_review status                              │
    │                                                              │
    │ Human feedback re-enters at Planner (not at Parser)          │
    └──────────────────────────────────────────────────────────────┘
    """
    snapshot = store.load_snapshot(run_id)

    def on_llm_start(agent_name: str) -> None:
        try:
            current_snap = store.load_snapshot(run_id)
            store.log(
                current_snap,
                agent_name,
                "Calling LLM API...",
                {"event": "llm_start"},
            )
        except Exception:
            pass

    def on_llm_end(agent_name: str, duration_ms: int) -> None:
        try:
            current_snap = store.load_snapshot(run_id)
            store.log(
                current_snap,
                agent_name,
                "LLM API call complete.",
                {"event": "llm_end", "duration_ms": duration_ms},
            )
        except Exception:
            pass

    # ── Shared LLM client (one Ollama connection, all agents) ──────────────
    llm = LLMClient(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        timeout=settings.llm_timeout,
        retries=settings.llm_retries,
        on_llm_start=on_llm_start,
        on_llm_end=on_llm_end,
    )

    parser = PaperParserAgent(llm)
    planner = PlannerAgent(llm)
    builder = BuilderAgent(llm)
    tester = TestingAgent(llm)
    evaluator = EvaluatorAgent(llm)

    try:
        # ── STEP 1: Parse PDF (once per run, cached in snapshot) ───────────
        if snapshot.state.knowledge is None:
            snapshot.state.status = RunStatus.parsing
            store.log(snapshot, AgentName.parser, "Parsing PDF into structured knowledge.", {"event": "start"})
            store.save_snapshot(snapshot)
            _t0 = time.monotonic()
            snapshot.state.knowledge = parser.run(pdf_path)
            _dur = round((time.monotonic() - _t0) * 1000)
            store.log(snapshot, AgentName.parser, "PDF parsing complete.", {"event": "end", "duration_ms": _dur})
            store.save_knowledge(run_id, snapshot.state.knowledge)
            store.checkpoint(snapshot, "parsed")
            log.info("parsed", run_id=run_id, title=snapshot.state.knowledge.paper.metadata.title)

        max_iterations = max(settings.max_iterations, 1)

        # ── Human feedback → append to state (re-enters at planner) ────────
        if feedback:
            snapshot.state.human_feedback.append(feedback.strip())
            # Reset iteration so planner gets at least one more pass
            if snapshot.state.iteration >= max_iterations:
                snapshot.state.iteration = max(snapshot.state.iteration - 1, 0)
            store.log(
                snapshot,
                AgentName.orchestrator,
                "Human feedback received — re-planning.",
                {"feedback": feedback.strip()},
            )

        # ── OUTER LOOP: plan → build-test → evaluate ───────────────────────
        for iteration in range(snapshot.state.iteration + 1, max_iterations + 1):
            snapshot.state.iteration = iteration

            # Collect all feedback (evaluator + human) for planner
            all_feedback = snapshot.state.evaluation_feedback + snapshot.state.human_feedback

            # ── Plan ────────────────────────────────────────────────────────
            snapshot.state.status = RunStatus.planning
            store.log(
                snapshot,
                AgentName.planner,
                "Creating implementation plan.",
                {"event": "start", "iteration": iteration, "feedback_items": len(all_feedback)},
            )
            store.save_snapshot(snapshot)
            _t0 = time.monotonic()
            snapshot.state.plan = planner.run((snapshot.state.knowledge, all_feedback, iteration))
            _dur = round((time.monotonic() - _t0) * 1000)
            store.log(
                snapshot,
                AgentName.planner,
                f"Plan complete — {len(snapshot.state.plan.tasks)} tasks.",
                {"event": "end", "duration_ms": _dur, "tasks": len(snapshot.state.plan.tasks)},
            )
            store.checkpoint(snapshot, f"iter{iteration:02d}-planned")

            # ── INNER LOOP: build → test (up to MAX_BUILD_ATTEMPTS) ─────────
            project_dir = store.run_dir(run_id) / "project"
            prev_diagnostics = None

            for build_attempt in range(1, MAX_BUILD_ATTEMPTS + 1):
                snapshot.state.build_attempt = build_attempt

                # Build (pass previous test errors for repair mode)
                snapshot.state.status = RunStatus.building
                store.log(
                    snapshot,
                    AgentName.builder,
                    f"Generating code (attempt {build_attempt}/{MAX_BUILD_ATTEMPTS}).",
                    {"event": "start", "tasks": len(snapshot.state.plan.tasks), "repair": prev_diagnostics is not None},
                )
                store.save_snapshot(snapshot)
                _t0 = time.monotonic()
                snapshot.state.build = builder.run(
                    (snapshot.state.knowledge, snapshot.state.plan, project_dir, prev_diagnostics)
                )
                _dur = round((time.monotonic() - _t0) * 1000)
                store.log(
                    snapshot,
                    AgentName.builder,
                    f"Code generation complete (attempt {build_attempt}).",
                    {"event": "end", "duration_ms": _dur, "artifacts": len(snapshot.state.build.artifacts)},
                )
                store.checkpoint(snapshot, f"iter{iteration:02d}-build{build_attempt}")

                # ── Create venv & install deps (once per build attempt) ─────
                store.log(
                    snapshot,
                    AgentName.orchestrator,
                    "Creating isolated venv for generated project.",
                    {"event": "venv_start"},
                )
                store.save_snapshot(snapshot)
                try:
                    VenvManager.create_venv(project_dir)
                    deps_ok = VenvManager.install_requirements(project_dir)
                    venv_python = VenvManager.get_python_path(project_dir)
                    store.log(
                        snapshot,
                        AgentName.orchestrator,
                        f"Venv ready (deps installed: {deps_ok}).",
                        {"event": "venv_end", "deps_installed": deps_ok, "python": str(venv_python)},
                    )
                except Exception as venv_exc:
                    venv_python = None
                    store.log(
                        snapshot,
                        AgentName.orchestrator,
                        f"Venv setup failed — falling back to system Python. Error: {venv_exc}",
                        {"event": "venv_end", "error": str(venv_exc)},
                        level="warning",
                    )

                # Test
                snapshot.state.status = RunStatus.testing
                store.log(
                    snapshot,
                    AgentName.tester,
                    f"Running tests (attempt {build_attempt}/{MAX_BUILD_ATTEMPTS}).",
                    {"event": "start"},
                )
                store.save_snapshot(snapshot)
                _t0 = time.monotonic()
                snapshot.state.diagnostics = tester.run(
                    (snapshot.state.build, snapshot.state.knowledge, venv_python)
                )
                _dur = round((time.monotonic() - _t0) * 1000)
                store.log(
                    snapshot,
                    AgentName.tester,
                    "Test run complete.",
                    {"event": "end", "duration_ms": _dur, "passed": snapshot.state.diagnostics.passed},
                )

                # Store errors for next build attempt
                snapshot.state.build_errors = snapshot.state.diagnostics.errors
                store.checkpoint(snapshot, f"iter{iteration:02d}-test{build_attempt}")

                if snapshot.state.diagnostics.passed:
                    store.log(
                        snapshot,
                        AgentName.tester,
                        "All tests passed.",
                        {"attempt": build_attempt},
                    )
                    break

                # Tests failed
                store.log(
                    snapshot,
                    AgentName.tester,
                    f"Tests failed (attempt {build_attempt}). {'Retrying builder.' if build_attempt < MAX_BUILD_ATTEMPTS else 'Max attempts reached.'}",
                    {"errors": snapshot.state.diagnostics.errors[:5]},
                    level="warning",
                )
                prev_diagnostics = snapshot.state.diagnostics

            # ── Evaluate ─────────────────────────────────────────────────────
            snapshot.state.status = RunStatus.evaluating
            store.log(snapshot, AgentName.evaluator, "Evaluating implementation fidelity against paper.", {"event": "start"})
            store.save_snapshot(snapshot)
            _t0 = time.monotonic()
            snapshot.state.evaluation = evaluator.run(
                (snapshot.state.knowledge, snapshot.state.build, snapshot.state.diagnostics)
            )
            _dur = round((time.monotonic() - _t0) * 1000)
            store.log(
                snapshot,
                AgentName.evaluator,
                f"Evaluation complete — score {snapshot.state.evaluation.overall_match:.1f}%.",
                {"event": "end", "duration_ms": _dur, "score": snapshot.state.evaluation.overall_match},
            )
            store.checkpoint(snapshot, f"iter{iteration:02d}-evaluated")

            score = snapshot.state.evaluation.overall_match
            log.info(
                "evaluation_result",
                run_id=run_id,
                iteration=iteration,
                score=score,
                complete=snapshot.state.evaluation.complete,
                missing=len(snapshot.state.evaluation.missing),
            )

            # ── SUCCESS ───────────────────────────────────────────────────────
            if snapshot.state.evaluation.complete:
                snapshot.state.status = RunStatus.completed
                store.log(
                    snapshot,
                    AgentName.orchestrator,
                    "✅ Paper successfully replicated! Implementation matches paper.",
                    {
                        "score": score,
                        "iterations": iteration,
                        "build_attempts": build_attempt,
                    },
                )
                store.save_snapshot(snapshot)
                store.archive_project(run_id)
                log.info("replication_success", run_id=run_id, score=score, iterations=iteration)
                return

            # ── Not complete — accumulate planner feedback for next iteration ─
            new_feedback = snapshot.state.evaluation.planner_feedback or snapshot.state.evaluation.missing
            snapshot.state.evaluation_feedback.extend(new_feedback)
            # Deduplicate keeping order
            seen: set[str] = set()
            snapshot.state.evaluation_feedback = [
                f for f in snapshot.state.evaluation_feedback if not (f in seen or seen.add(f))  # type: ignore[func-returns-value]
            ]

            store.log(
                snapshot,
                AgentName.orchestrator,
                f"Score {score:.1f}% — not complete. Replanning for iteration {iteration + 1}.",
                {"missing": snapshot.state.evaluation.missing[:5], "score": score},
                level="warning",
            )
            store.save_snapshot(snapshot)

        # ── OUTER LOOP EXHAUSTED → human review ──────────────────────────────
        snapshot.state.status = RunStatus.human_review
        store.log(
            snapshot,
            AgentName.orchestrator,
            f"⚠️ Max iterations ({max_iterations}) exhausted. Project ready for human review.",
            {
                "final_score": snapshot.state.evaluation.overall_match if snapshot.state.evaluation else 0,
                "missing": snapshot.state.evaluation.missing if snapshot.state.evaluation else [],
            },
        )
        store.archive_project(run_id)
        store.save_snapshot(snapshot)
        log.info("replication_human_review", run_id=run_id, iterations=max_iterations)

    except Exception as exc:
        snapshot.state.status = RunStatus.failed
        store.log(
            snapshot,
            AgentName.orchestrator,
            "❌ Replication failed with unexpected error.",
            {"error": str(exc), "type": type(exc).__name__},
            level="error",
        )
        store.save_snapshot(snapshot)
        log.error("replication_failed", run_id=run_id, error=str(exc))
        raise
