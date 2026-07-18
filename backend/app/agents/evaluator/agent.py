from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.base import LLMAgent
from app.domain.schemas import BuildResult, EvaluationReport, KnowledgeBundle, TestDiagnostics
from app.services.llm import LLMClient

_SYS_EVAL = """\
You are a senior computer vision researcher reviewing a software implementation.
Your job: assess how faithfully the generated Python code replicates the described paper architecture.

Scoring criteria (total 100 points):
  40pts — All named architectural components from the paper appear as nn.Module submodules
  20pts — Loss function interfaces match paper's described objectives
  20pts — Preprocessing and postprocessing pipelines match paper description
  10pts — Inference pipeline correctly chains all components
  10pts — All smoke tests pass without GPU or data

Return a SINGLE valid JSON object:
{
  "overall_match": float (0-100),
  "missing": ["component or feature missing from implementation"],
  "extra": ["implemented but not in paper"],
  "recommendations": ["concrete actionable fix for planner"],
  "complete": bool (true ONLY if overall_match >= 90 AND tests_passed is true),
  "planner_feedback": ["specific instruction for planner: what to add/fix/remove"]
}

Be specific in planner_feedback — these go directly to the planner agent.
Return ONLY the JSON object.\
"""


class EvaluatorAgent(LLMAgent):
    """
    Evaluates implementation fidelity against paper knowledge.

    Uses LLM to:
    - Compare generated code (model.py, losses.py, etc.) against paper architecture
    - Score match 0-100
    - List what's missing, what's extra
    - Produce actionable planner_feedback for the next iteration

    Fallback: rule-based scoring if LLM fails.
    """

    name = "evaluator"

    def __init__(self, llm: LLMClient | None = None) -> None:
        super().__init__(llm)

    def run(
        self,
        payload: tuple[KnowledgeBundle, BuildResult, TestDiagnostics],
    ) -> EvaluationReport:
        knowledge, build, diagnostics = payload
        project_root = Path(build.project_root)
        paper = knowledge.paper

        self.log.info("evaluating", project_root=str(project_root))

        # Read generated source files
        model_code = self._read(project_root / "src" / "replicated_paper" / "model.py")
        losses_code = self._read(project_root / "src" / "replicated_paper" / "losses.py")
        inference_code = self._read(project_root / "src" / "replicated_paper" / "inference.py")

        # Build user prompt
        user = self._build_user_prompt(paper, model_code, losses_code, inference_code, diagnostics)

        result = self._ask_json(_SYS_EVAL, user, fallback={})

        def _as_list(val: Any) -> list[str]:
            if not val:
                return []
            if isinstance(val, list):
                return [str(item) for item in val]
            if isinstance(val, str):
                return [val]
            return [str(val)]

        if result and isinstance(result.get("overall_match"), (int, float)):
            try:
                report = EvaluationReport(
                    overall_match=float(min(100.0, max(0.0, result["overall_match"]))),
                    missing=_as_list(result.get("missing")),
                    extra=_as_list(result.get("extra")),
                    recommendations=_as_list(result.get("recommendations")),
                    complete=bool(result.get("complete", False)) and diagnostics.passed,
                    planner_feedback=_as_list(result.get("planner_feedback")),
                )
                self.log.info(
                    "evaluation_complete",
                    score=report.overall_match,
                    complete=report.complete,
                    missing=len(report.missing),
                    llm=True,
                )
                return report
            except Exception as exc:
                self.log.warning("evaluation_parse_failed", error=str(exc))

        # Fallback rule-based evaluation
        return self._fallback_eval(paper, project_root, model_code, diagnostics)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_user_prompt(
        self,
        paper,
        model_code: str,
        losses_code: str,
        inference_code: str,
        diagnostics: TestDiagnostics,
    ) -> str:
        return f"""\
Paper: {paper.metadata.title}

Expected architectural components: {paper.architecture!r}
Expected backbone: {paper.backbone or "None"}
Expected loss functions: {paper.loss_functions!r}
Expected preprocessing: {paper.preprocessing!r}
Expected postprocessing: {paper.postprocessing!r}

Tests passed: {diagnostics.passed}
Test errors: {diagnostics.errors[:5]!r}

--- Generated model.py ---
{self._truncate(model_code, 3000)}

--- Generated losses.py ---
{self._truncate(losses_code, 1500)}

--- Generated inference.py ---
{self._truncate(inference_code, 1500)}
"""

    # ------------------------------------------------------------------
    # Fallback rule-based scorer
    # ------------------------------------------------------------------

    def _fallback_eval(
        self,
        paper,
        project_root: Path,
        model_code: str,
        diagnostics: TestDiagnostics,
    ) -> EvaluationReport:
        self.log.info("evaluation_fallback")
        missing: list[str] = []
        recommendations: list[str] = []

        # Check architecture components in model code
        for component in paper.architecture:
            if component.lower() not in model_code.lower():
                missing.append(f"Architecture component not found in model.py: {component}")

        # Check loss files exist
        if paper.loss_functions:
            losses_path = project_root / "src" / "replicated_paper" / "losses.py"
            if not losses_path.exists():
                missing.append("losses.py not generated")
            else:
                losses_code = losses_path.read_text(encoding="utf-8")
                for loss in paper.loss_functions:
                    if loss.lower() not in losses_code.lower():
                        missing.append(f"Loss function not referenced: {loss}")

        if not diagnostics.passed:
            missing.append("Tests not passing")
            recommendations.extend(diagnostics.errors[:5])

        required_count = max(len(paper.architecture) + 2, 3)
        score = 100.0 * (required_count - min(len(missing), required_count)) / required_count
        complete = diagnostics.passed and score >= 90.0

        planner_feedback = [f"Implement missing: {m}" for m in missing[:5]]

        return EvaluationReport(
            overall_match=round(score, 2),
            missing=missing,
            extra=[],
            recommendations=recommendations,
            complete=complete,
            planner_feedback=planner_feedback,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8") if path.exists() else ""
        except Exception:
            return ""
