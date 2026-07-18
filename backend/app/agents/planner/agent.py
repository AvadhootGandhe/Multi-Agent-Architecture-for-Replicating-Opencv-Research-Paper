from __future__ import annotations

import json

from app.agents.base import LLMAgent
from app.domain.schemas import ImplementationPlan, KnowledgeBundle, PlanTask
from app.services.llm import LLMClient

_SYSTEM = """\
You are a senior computer vision engineer creating an implementation plan to replicate a CV research paper.

STRICT CONSTRAINTS — this is a software scaffold, NOT a reproduction study:
- NO dataset downloading or loading
- NO model training (no training loops, no gradient computation during tests)
- NO benchmark reproduction
- NO pretrained weights download
- Implement ONLY: model architecture, loss function interfaces, preprocessing pipeline, inference runner, smoke tests
- Use PyTorch (torch.nn) as the deep learning framework
- All code must run on CPU without GPU

Your plan must produce exactly these files:
1. src/replicated_paper/config.py       — ModelConfig (pydantic)
2. src/replicated_paper/model.py        — ReplicatedModel (nn.Module) with real architecture
3. src/replicated_paper/losses.py       — Loss function callables
4. src/replicated_paper/preprocessing.py — PreprocessingPipeline
5. src/replicated_paper/postprocessing.py — PostProcessor
6. src/replicated_paper/inference.py    — InferenceRunner chaining pre→model→post
7. tests/test_smoke.py                  — Smoke tests (no GPU, no data)
8. requirements.txt                     — Python dependencies
9. README.md                            — Paper summary and usage

Return a SINGLE valid JSON object:
{
  "summary": "string — one sentence describing the implementation goal",
  "tasks": [
    {
      "id": "string — snake_case unique id",
      "title": "string",
      "description": "string — precise technical description",
      "dependencies": ["task_id"],
      "target_files": ["path/to/file.py"],
      "acceptance_criteria": ["string — measurable criterion"]
    }
  ]
}

Return ONLY the JSON object.\
"""


class PlannerAgent(LLMAgent):
    """
    Creates a concrete implementation task DAG from paper knowledge.

    Inputs:
    - KnowledgeBundle: full parsed paper knowledge
    - feedback: list of strings from evaluator (what's missing/excessive) or human
    - iteration: current run number

    Output: ImplementationPlan with ordered tasks.
    Fallback: hard-coded task list if LLM fails.
    """

    name = "planner"

    def __init__(self, llm: LLMClient | None = None) -> None:
        super().__init__(llm)

    def run(self, payload: tuple[KnowledgeBundle, list[str], int]) -> ImplementationPlan:
        knowledge, feedback, revision = payload
        paper = knowledge.paper

        self.log.info("planning", revision=revision, feedback_items=len(feedback))

        user = self._build_user_prompt(paper, feedback, revision)
        result = self._ask_json(_SYSTEM, user, fallback={})

        if result and result.get("tasks"):
            try:
                tasks = [PlanTask(**t) for t in result["tasks"]]
                plan = ImplementationPlan(
                    summary=result.get("summary", f"Implement '{paper.metadata.title}' architecture scaffold."),
                    tasks=tasks,
                    dependency_graph={t.id: t.dependencies for t in tasks},
                    revision=revision,
                    addressing_feedback=feedback,
                )
                self.log.info("planning_complete", tasks=len(tasks), llm=True)
                return plan
            except Exception as exc:
                self.log.warning("plan_parse_failed", error=str(exc))

        # Fallback — deterministic task list
        self.log.info("planning_fallback", revision=revision)
        return self._fallback_plan(paper, feedback, revision)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_user_prompt(self, paper, feedback: list[str], revision: int) -> str:
        parts = [
            f"Paper title: {paper.metadata.title}",
            f"Revision: {revision}",
            f"Architecture components: {', '.join(paper.architecture) or 'Not specified'}",
            f"Backbone: {paper.backbone or 'Generic CNN'}",
            f"Loss functions: {', '.join(paper.loss_functions) or 'MSE loss'}",
            f"Preprocessing steps: {', '.join(paper.preprocessing) or 'resize, normalize'}",
            f"Postprocessing steps: {', '.join(paper.postprocessing) or 'argmax'}",
            f"External libraries: {', '.join(paper.external_libraries)}",
            f"Hyperparameters: {json.dumps(paper.hyperparameters)}",
            f"Key implementation notes: {'; '.join(paper.implementation_notes[:5]) or 'None'}",
            f"Pseudocode available: {bool(paper.pseudocode)}",
        ]
        if getattr(paper, "raw_text", None):
            truncated_text = self._truncate(paper.raw_text, max_chars=15000)
            parts.append(f"\nFULL PAPER TEXT:\n{truncated_text}")

        if feedback:
            parts.append("\nFEEDBACK TO ADDRESS IN THIS REVISION:")
            parts.extend(f"  - {item}" for item in feedback)
            parts.append("\nMake sure your plan EXPLICITLY addresses each feedback item above.")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Fallback plan (rule-based, always valid)
    # ------------------------------------------------------------------

    def _fallback_plan(self, paper, feedback: list[str], revision: int) -> ImplementationPlan:
        arch_str = ", ".join(paper.architecture[:6]) or "encoder, decoder"
        loss_str = ", ".join(paper.loss_functions) or "mse_loss"
        tasks = [
            PlanTask(
                id="config",
                title="Create ModelConfig",
                description=f"Pydantic config for '{paper.metadata.title}': backbone={paper.backbone}, losses={loss_str}, input_size from hyperparams.",
                target_files=["src/replicated_paper/config.py"],
                acceptance_criteria=["ModelConfig imports without error.", "DEFAULT_CONFIG instantiates."],
            ),
            PlanTask(
                id="model",
                title="Implement model architecture",
                description=f"ReplicatedModel (nn.Module) with components: {arch_str}. Forward pass deterministic, CPU-only.",
                dependencies=["config"],
                target_files=["src/replicated_paper/model.py"],
                acceptance_criteria=["Model instantiates.", "forward() returns dict with 'logits' key.", "No GPU required."],
            ),
            PlanTask(
                id="losses",
                title="Implement loss functions",
                description=f"Callable loss implementations for: {loss_str}. Return scalar float.",
                dependencies=["config"],
                target_files=["src/replicated_paper/losses.py"],
                acceptance_criteria=["compute_loss() callable with logits tensor.", "Returns float."],
            ),
            PlanTask(
                id="preprocessing",
                title="Implement preprocessing pipeline",
                description=f"PreprocessingPipeline class. Steps: {', '.join(paper.preprocessing) or 'resize to 224x224, normalize'}. Input: numpy array. Output: torch.Tensor batch.",
                dependencies=["config"],
                target_files=["src/replicated_paper/preprocessing.py"],
                acceptance_criteria=["Accepts numpy uint8 image.", "Returns float32 tensor shape (1, C, H, W)."],
            ),
            PlanTask(
                id="postprocessing",
                title="Implement postprocessing",
                description=f"PostProcessor class. Steps: {', '.join(paper.postprocessing) or 'argmax, scores'}. Input: model output dict.",
                dependencies=["model"],
                target_files=["src/replicated_paper/postprocessing.py"],
                acceptance_criteria=["Returns dict with 'scores' and 'predicted_class'."],
            ),
            PlanTask(
                id="inference",
                title="Implement inference runner",
                description="InferenceRunner wiring PreprocessingPipeline → ReplicatedModel → PostProcessor. predict(image) and predict_shape(shape) methods.",
                dependencies=["preprocessing", "model", "postprocessing"],
                target_files=["src/replicated_paper/inference.py"],
                acceptance_criteria=["predict_shape((1,3,224,224)) returns dict.", "No GPU required."],
            ),
            PlanTask(
                id="tests",
                title="Write smoke tests",
                description="pytest smoke tests: config loads, model forward passes, inference on random numpy array, loss computable.",
                dependencies=["inference", "losses"],
                target_files=["tests/test_smoke.py"],
                acceptance_criteria=["All tests pass without data download.", "Tests run on CPU."],
            ),
        ]
        if feedback:
            tasks.append(
                PlanTask(
                    id=f"feedback_revision_{revision}",
                    title="Address feedback",
                    description="; ".join(feedback[:5]),
                    dependencies=["tests"],
                    target_files=["src/replicated_paper/model.py", "README.md"],
                    acceptance_criteria=["Each feedback item reflected in code or docs."],
                )
            )
        return ImplementationPlan(
            summary=f"Architecture scaffold for '{paper.metadata.title}'. No training, no datasets.",
            tasks=tasks,
            dependency_graph={t.id: t.dependencies for t in tasks},
            revision=revision,
            addressing_feedback=feedback,
        )
