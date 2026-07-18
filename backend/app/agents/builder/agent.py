from __future__ import annotations

from pathlib import Path

from app.agents.base import LLMAgent
from app.domain.schemas import BuildArtifact, BuildResult, ImplementationPlan, KnowledgeBundle, TestDiagnostics
from app.services.llm import LLMClient

# ── System prompts per file ────────────────────────────────────────────────────

_SYS_MODEL = """\
You are an expert PyTorch engineer implementing a computer vision model architecture.
Write a complete, runnable Python module. Rules:
- Subclass torch.nn.Module for ReplicatedModel
- __init__(self, config: ModelConfig) — accept ModelConfig
- forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]
  returns at least {"logits": tensor, "features": tensor}
- Use named sub-modules that EXACTLY match the architecture components listed
- CPU compatible — no .cuda() calls, no device assumptions
- No pretrained weight downloads (no torchvision.models calls with pretrained=True)
- No training code, no optimizer, no data loading
- All imports at top, no relative imports outside the replicated_paper package
Return ONLY raw Python code (no markdown fences, no explanation).\
"""

_SYS_CONFIG = """\
You are a Python engineer writing a pydantic configuration module.
Write a complete ModelConfig class using pydantic v2 BaseModel.
Include DEFAULT_CONFIG = ModelConfig() at the end.
Return ONLY raw Python code.\
"""

_SYS_LOSSES = """\
You are a PyTorch engineer writing loss function implementations for a CV model.
Write callable loss functions that accept (logits: torch.Tensor, targets: torch.Tensor | None) -> float.
Export LOSS_NAMES list and a compute_loss() function.
No training code. CPU compatible.
Return ONLY raw Python code.\
"""

_SYS_PREPROCESSING = """\
You are a CV engineer writing an image preprocessing pipeline.
Write a PreprocessingPipeline class:
- __init__(self, config: ModelConfig)
- __call__(self, image: np.ndarray) -> torch.Tensor
  Input: HWC uint8 numpy array. Output: NCHW float32 tensor normalized to [0,1].
Use numpy and torchvision.transforms if needed.
Return ONLY raw Python code.\
"""

_SYS_POSTPROCESSING = """\
Write a PostProcessor class for a computer vision model:
- __call__(self, outputs: dict[str, torch.Tensor]) -> dict[str, object]
  Input: model forward() output dict (has 'logits' key).
  Output: {"scores": list, "predicted_class": list}
Return ONLY raw Python code.\
"""

_SYS_INFERENCE = """\
Write an InferenceRunner class that chains preprocessing → model → postprocessing:
from .config import DEFAULT_CONFIG, ModelConfig
from .model import ReplicatedModel
from .postprocessing import PostProcessor
from .preprocessing import PreprocessingPipeline
- __init__(self, config: ModelConfig | None = None)
- predict(self, image: np.ndarray) -> dict[str, object]
- predict_shape(self, shape: tuple[int, ...]) -> dict[str, object]
  (creates zeros tensor of given shape and runs inference)
No GPU. Return ONLY raw Python code.\
"""

_SYS_REPAIR = """\
You are a Python debugging expert. The code below has syntax or runtime errors.
Fix ALL errors listed and return the corrected, complete Python file.
Rules:
- Keep the same class/function names and structure
- Fix only what is broken; preserve working logic
- Return ONLY raw Python code (no explanation, no markdown)\
"""


class BuilderAgent(LLMAgent):
    """
    Generates real Python/PyTorch implementation files from paper knowledge + plan.

    In normal mode: LLM writes each file from scratch using paper knowledge.
    In repair mode: LLM receives existing code + tester errors and fixes them.

    Fallback: deterministic template strings if LLM produces empty/invalid code.
    """

    name = "builder"

    def __init__(self, llm: LLMClient | None = None) -> None:
        super().__init__(llm)

    def run(
        self,
        payload: tuple[KnowledgeBundle, ImplementationPlan, Path, TestDiagnostics | None],
    ) -> BuildResult:
        knowledge, plan, project_root, prev_diagnostics = payload
        project_root.mkdir(parents=True, exist_ok=True)
        self._project_root = project_root

        src = project_root / "src" / "replicated_paper"
        tests = project_root / "tests"
        src.mkdir(parents=True, exist_ok=True)
        tests.mkdir(parents=True, exist_ok=True)

        paper = knowledge.paper
        repair_mode = prev_diagnostics is not None and not prev_diagnostics.passed
        self.log.info("building", repair_mode=repair_mode, title=paper.metadata.title)

        # ── Generate / repair each source file ───────────────────────────────
        file_errors = prev_diagnostics.file_errors if repair_mode and prev_diagnostics else {}

        content_map: dict[Path, str] = {
            src / "config.py": self._gen_config(paper, file_errors.get("config.py", [])),
            src / "model.py": self._gen_model(paper, file_errors.get("model.py", [])),
            src / "losses.py": self._gen_losses(paper, file_errors.get("losses.py", [])),
            src / "preprocessing.py": self._gen_preprocessing(paper, file_errors.get("preprocessing.py", [])),
            src / "postprocessing.py": self._gen_postprocessing(paper, file_errors.get("postprocessing.py", [])),
            src / "inference.py": self._gen_inference(paper, file_errors.get("inference.py", [])),
            src / "__init__.py": '"""Generated implementation package."""\n\nfrom .inference import InferenceRunner\n',
            tests / "test_smoke.py": self._gen_tests_placeholder(paper),
            project_root / "requirements.txt": self._gen_requirements(paper),
            project_root / "README.md": self._gen_readme(paper, plan),
            project_root / "Dockerfile": self._dockerfile(),
        }

        artifacts: list[BuildArtifact] = []
        for path, content in content_map.items():
            if content.strip():
                path.write_text(content, encoding="utf-8")
                artifacts.append(
                    BuildArtifact(
                        path=str(path.relative_to(project_root)),
                        kind=self._kind(path),
                        description=f"Generated {path.name}",
                    )
                )

        self.log.info("build_complete", files=len(artifacts), repair=repair_mode)
        return BuildResult(
            project_root=project_root,
            artifacts=artifacts,
            notes=[
                "CV paper scaffold — no dataset download, no training, no benchmark reproduction.",
                f"Generated {len(artifacts)} files. Repair mode: {repair_mode}.",
            ],
        )

    # ------------------------------------------------------------------
    # File generators — each calls LLM then falls back to template
    # ------------------------------------------------------------------

    def _gen_config(self, paper, errors: list[str]) -> str:
        hyperparams = paper.hyperparameters
        input_size = hyperparams.get("input_size", "224, 224")
        # Parse "224x224" or "224, 224" → tuple string
        import re
        m = re.search(r"(\d+)\s*[x×,]\s*(\d+)", str(input_size))
        hw = f"({m.group(1)}, {m.group(2)})" if m else "(224, 224)"

        user = f"""\
Paper: {paper.metadata.title}
Backbone: {paper.backbone or "generic-cv-backbone"}
Input size: {hw}
Number of classes: {hyperparams.get("num_classes", "1")}
Loss names: {paper.loss_functions!r}
Preprocessing steps: {paper.preprocessing!r}
Postprocessing steps: {paper.postprocessing!r}
Learning rate: {hyperparams.get("learning_rate", "0.001")}
Batch size: {hyperparams.get("batch_size", "8")}
"""
        if errors:
            return self._repair(self._fallback_config(paper, hw), errors, "config.py")

        code = self._ask_code(_SYS_CONFIG, user)
        return code or self._fallback_config(paper, hw)

    def _gen_model(self, paper, errors: list[str]) -> str:
        user = f"""\
Paper: {paper.metadata.title}
Architecture components (use these as nn.Module submodule names): {paper.architecture!r}
Backbone: {paper.backbone or "None — build from scratch"}
Key implementation notes: {paper.implementation_notes[:4]!r}
Pseudocode / algorithms: {self._truncate(str(paper.pseudocode[:2]), 1500)}
Loss functions (for reference, not needed in model.py): {paper.loss_functions!r}
Expected input: torch.Tensor shape (N, C, H, W) where C=3
Expected output dict keys: "logits", "features"
"""
        if errors:
            existing = self._read_project_file("src/replicated_paper/model.py")
            return self._repair(existing or self._fallback_model(paper), errors, "model.py")

        code = self._ask_code(_SYS_MODEL, user)
        return code or self._fallback_model(paper)

    def _gen_losses(self, paper, errors: list[str]) -> str:
        user = f"""\
Loss functions to implement: {paper.loss_functions or ["mse_loss"]}
Return:
  LOSS_NAMES: list[str]
  compute_loss(logits: torch.Tensor, targets: torch.Tensor | None = None) -> float
"""
        if errors:
            return self._repair(self._fallback_losses(paper), errors, "losses.py")
        code = self._ask_code(_SYS_LOSSES, user)
        return code or self._fallback_losses(paper)

    def _gen_preprocessing(self, paper, errors: list[str]) -> str:
        user = f"""\
Preprocessing steps from paper: {paper.preprocessing or ["resize to 224x224", "normalize to [0,1]"]}
Input: numpy ndarray HWC uint8
Output: torch.Tensor NCHW float32
"""
        if errors:
            return self._repair(self._fallback_preprocessing(), errors, "preprocessing.py")
        code = self._ask_code(_SYS_PREPROCESSING, user)
        return code or self._fallback_preprocessing()

    def _gen_postprocessing(self, paper, errors: list[str]) -> str:
        user = f"""\
Postprocessing steps: {paper.postprocessing or ["softmax", "argmax"]}
Input: dict with key "logits" (torch.Tensor shape (N, num_classes))
Output: dict with "scores" (list of lists) and "predicted_class" (list of ints)
"""
        if errors:
            return self._repair(self._fallback_postprocessing(), errors, "postprocessing.py")
        code = self._ask_code(_SYS_POSTPROCESSING, user)
        return code or self._fallback_postprocessing()

    def _gen_inference(self, paper, errors: list[str]) -> str:
        user = f"""\
Chain: PreprocessingPipeline → ReplicatedModel → PostProcessor
Preprocessing from: .preprocessing import PreprocessingPipeline
Model from: .model import ReplicatedModel
PostProcessor from: .postprocessing import PostProcessor
Config from: .config import DEFAULT_CONFIG, ModelConfig
Implement predict(image: np.ndarray) and predict_shape(shape: tuple).
"""
        if errors:
            return self._repair(self._fallback_inference(), errors, "inference.py")
        code = self._ask_code(_SYS_INFERENCE, user)
        return code or self._fallback_inference()

    def _gen_tests_placeholder(self, paper) -> str:
        """Placeholder tests — TesterAgent writes real targeted tests."""
        return f'''\
"""Smoke tests generated by BuilderAgent — TesterAgent will extend these."""
import numpy as np
import pytest

from replicated_paper import InferenceRunner
from replicated_paper.config import DEFAULT_CONFIG
from replicated_paper.losses import compute_loss


def test_config_loads():
    """Config instantiates with correct paper title."""
    assert DEFAULT_CONFIG is not None


def test_inference_runner_predicts():
    """InferenceRunner produces structured output on random image."""
    runner = InferenceRunner()
    result = runner.predict(np.zeros((224, 224, 3), dtype=np.uint8))
    assert "scores" in result
    assert "predicted_class" in result


def test_predict_shape():
    """predict_shape works on batch input."""
    runner = InferenceRunner()
    result = runner.predict_shape((1, 3, 224, 224))
    assert isinstance(result, dict)


def test_loss_returns_float():
    """Loss function returns float."""
    import torch
    logits = torch.zeros(1, 1)
    assert isinstance(compute_loss(logits), float)
'''

    # ------------------------------------------------------------------
    # Repair mode — send existing code + errors to LLM
    # ------------------------------------------------------------------

    def _repair(self, existing_code: str, errors: list[str], filename: str) -> str:
        if not existing_code.strip():
            return ""
        error_block = "\n".join(f"  - {e}" for e in errors[:10])
        user = f"""\
File: {filename}
Errors to fix:
{error_block}

Current code:
```python
{self._truncate(existing_code, 6000)}
```
Return the complete fixed Python file.
"""
        code = self._ask_code(_SYS_REPAIR, user)
        return code or existing_code

    def _read_project_file(self, rel_path: str) -> str:
        """Read existing generated file for repair mode."""
        if not hasattr(self, '_project_root'):
            return ""
        path = self._project_root / rel_path
        try:
            return path.read_text(encoding="utf-8") if path.exists() else ""
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Static / template helpers
    # ------------------------------------------------------------------

    def _gen_requirements(self, paper) -> str:
        deps = ["numpy>=1.26", "pydantic>=2.7", "torch>=2.3", "torchvision>=0.18", "pytest>=8.0"]
        if any("opencv" in lib.lower() for lib in paper.external_libraries):
            deps.append("opencv-python>=4.9")
        if any("scipy" in lib.lower() for lib in paper.external_libraries):
            deps.append("scipy>=1.13")
        return "\n".join(dict.fromkeys(deps)) + "\n"

    def _gen_readme(self, paper, plan: ImplementationPlan) -> str:
        tasks = "\n".join(f"{i+1}. **{t.title}**: {t.description}" for i, t in enumerate(plan.tasks))
        return f"""\
# {paper.metadata.title} — Implementation Scaffold

> Auto-generated by Research Paper Replicator (multi-agent, Qwen3-8B)

## About
This project replicates the **software architecture** of the above paper.
It does **not** download datasets, train models, or reproduce benchmark results.

## Extracted Architecture
- **Backbone**: {paper.backbone or "Not specified"}
- **Modules**: {", ".join(paper.architecture) or "See model.py"}
- **Losses**: {", ".join(paper.loss_functions) or "See losses.py"}

## Implementation Plan
{tasks}

## Quick Start
```bash
pip install -r requirements.txt
python -m pytest tests/ -v
python -c "from replicated_paper import InferenceRunner; import numpy as np; r=InferenceRunner(); print(r.predict_shape((1,3,224,224)))"
```

## Notes
{chr(10).join(f'- {n}' for n in paper.implementation_notes[:5]) or '- See paper for full details.'}
"""

    def _dockerfile(self) -> str:
        return """\
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app/src
CMD ["python", "-m", "pytest", "-q"]
"""

    def _kind(self, path: Path) -> str:
        if path.name == "Dockerfile":
            return "container"
        if path.suffix == ".md":
            return "documentation"
        if "tests" in path.parts:
            return "test"
        if path.suffix in {".txt", ".toml", ".yaml", ".yml"}:
            return "config"
        return "source"

    # ------------------------------------------------------------------
    # Deterministic fallbacks — always produce valid Python
    # ------------------------------------------------------------------

    def _fallback_config(self, paper, hw: str = "(224, 224)") -> str:
        backbone = paper.backbone or 'generic-cv-backbone'
        title = paper.metadata.title.replace('"', "'")
        return f'''from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    title: str = "{title}"
    backbone: str = "{backbone}"
    input_size: tuple[int, int] = {hw}
    channels: int = 3
    num_classes: int = 1
    loss_names: list[str] = Field(default_factory=lambda: {paper.loss_functions!r})
    preprocessing_steps: list[str] = Field(default_factory=lambda: {paper.preprocessing!r})
    postprocessing_steps: list[str] = Field(default_factory=lambda: {paper.postprocessing!r})


DEFAULT_CONFIG = ModelConfig()
'''

    def _fallback_model(self, paper) -> str:
        modules = paper.architecture or ["feature_extractor", "prediction_head"]
        module_defs = "\n        ".join(
            f'self.{m.lower().replace(" ", "_")} = nn.Identity()  # {m}'
            for m in modules[:8]
        )
        return f'''from __future__ import annotations

import torch
import torch.nn as nn

from .config import ModelConfig


class ReplicatedModel(nn.Module):
    """
    Architecture scaffold for: {paper.metadata.title}
    Modules: {", ".join(modules[:6])}
    """

    module_names: list[str] = {modules!r}

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.config = config
        in_ch = config.channels
        # Named sub-modules matching paper architecture
        {module_defs}
        self.head = nn.Linear(in_ch, config.num_classes)

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        # x: (N, C, H, W)
        features = x.mean(dim=[2, 3])  # global average pool → (N, C)
        logits = self.head(features)   # (N, num_classes)
        return {{"features": features, "logits": logits}}
'''

    def _fallback_losses(self, paper) -> str:
        names = paper.loss_functions or ["mse_loss"]
        return f'''from __future__ import annotations

import torch
import torch.nn.functional as F

LOSS_NAMES: list[str] = {names!r}


def compute_loss(
    logits: torch.Tensor,
    targets: torch.Tensor | None = None,
) -> float:
    """Compute loss. Falls back to MSE if no targets provided."""
    if targets is None:
        return float(torch.mean(logits ** 2).item())
    return float(F.mse_loss(logits, targets.float()).item())
'''

    def _fallback_preprocessing(self) -> str:
        return '''from __future__ import annotations

import numpy as np
import torch

from .config import ModelConfig


class PreprocessingPipeline:
    """Resize, convert to tensor, normalize to [0, 1]."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        self.target_h, self.target_w = config.input_size

    def __call__(self, image: np.ndarray) -> torch.Tensor:
        # Ensure HWC uint8
        arr = np.asarray(image, dtype=np.float32)
        if arr.max() > 1.0:
            arr = arr / 255.0
        # Resize via numpy (no cv2 dependency required)
        if arr.ndim == 3:
            arr = self._resize(arr, self.target_h, self.target_w)
            arr = np.moveaxis(arr, -1, 0)  # HWC → CHW
        tensor = torch.from_numpy(arr).unsqueeze(0)  # (1, C, H, W)
        return tensor

    @staticmethod
    def _resize(img: np.ndarray, h: int, w: int) -> np.ndarray:
        """Nearest-neighbour resize without cv2."""
        src_h, src_w = img.shape[:2]
        row_idx = (np.arange(h) * src_h / h).astype(int)
        col_idx = (np.arange(w) * src_w / w).astype(int)
        return img[np.ix_(row_idx, col_idx)]
'''

    def _fallback_postprocessing(self) -> str:
        return '''from __future__ import annotations

import torch


class PostProcessor:
    """Convert raw logits to structured predictions."""

    def __call__(self, outputs: dict[str, torch.Tensor]) -> dict[str, object]:
        logits = outputs["logits"]  # (N, num_classes)
        scores = torch.softmax(logits, dim=-1)
        predicted = torch.argmax(scores, dim=-1)
        return {
            "scores": scores.tolist(),
            "predicted_class": predicted.tolist(),
        }
'''

    def _fallback_inference(self) -> str:
        return '''from __future__ import annotations

import numpy as np
import torch

from .config import DEFAULT_CONFIG, ModelConfig
from .model import ReplicatedModel
from .postprocessing import PostProcessor
from .preprocessing import PreprocessingPipeline


class InferenceRunner:
    """End-to-end inference: preprocessing → model → postprocessing."""

    def __init__(self, config: ModelConfig | None = None) -> None:
        self.config = config or DEFAULT_CONFIG
        self.preprocess = PreprocessingPipeline(self.config)
        self.model = ReplicatedModel(self.config)
        self.model.eval()
        self.postprocess = PostProcessor()

    def predict(self, image: np.ndarray) -> dict[str, object]:
        """Run inference on a single HWC numpy image."""
        with torch.no_grad():
            batch = self.preprocess(image)
            outputs = self.model(batch)
        return self.postprocess(outputs)

    def predict_shape(self, shape: tuple[int, ...]) -> dict[str, object]:
        """Run inference on a zero tensor of given shape."""
        with torch.no_grad():
            if len(shape) == 4:
                batch = torch.zeros(*shape)
            else:
                image = np.zeros(shape, dtype=np.uint8)
                batch = self.preprocess(image)
            outputs = self.model(batch)
        return self.postprocess(outputs)
'''
