from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

from app.agents.base import LLMAgent
from app.domain.schemas import BuildResult, KnowledgeBundle, TestDiagnostics
from app.services.llm import LLMClient

_SYS_TESTS = """\
You are a Python testing expert specializing in computer vision models.
Write pytest smoke tests for the generated implementation.

Rules:
- NO dataset downloads, NO internet calls
- NO GPU required (CPU only)
- Test: config loads, model instantiates, forward pass runs on random tensor,
  inference pipeline end-to-end on random numpy array, loss computable
- Use numpy and torch only (both available)
- Introspect module_names, LOSS_NAMES if they exist
- Tests must be independent (no shared state)
- NO pretrained weight loading
Return ONLY raw Python code (no markdown, no explanation).\
"""


class TestingAgent(LLMAgent):
    """
    Tests the generated project.

    Steps:
    1. LLM reads generated model.py + inference.py and writes targeted tests
       (replaces placeholder test_smoke.py)
    2. py_compile all .py files (syntax check)
    3. Optionally run pytest in a subprocess (if pytest is importable)
    4. Returns TestDiagnostics with pass/fail + per-file error map for builder

    The per-file error map allows BuilderAgent to repair only the broken files.
    """

    name = "tester"

    def __init__(self, llm: LLMClient | None = None) -> None:
        super().__init__(llm)

    def run(self, payload: tuple[BuildResult, KnowledgeBundle] | tuple[BuildResult, KnowledgeBundle, Path | None]) -> TestDiagnostics:
        # Support both 2-tuple (legacy) and 3-tuple (with venv_python) payloads
        if len(payload) == 3:
            build, knowledge, venv_python = payload
        else:
            build, knowledge = payload[:2]
            venv_python = None
        project_root = Path(build.project_root)
        src = project_root / "src" / "replicated_paper"
        tests_dir = project_root / "tests"

        self.log.info("testing", project_root=str(project_root))
        checks: list[str] = []
        errors: list[str] = []
        file_errors: dict[str, list[str]] = {}

        # ── Step 1: LLM writes targeted tests ────────────────────────────────
        llm_tests = self._write_tests(src, knowledge)
        if llm_tests:
            test_file = tests_dir / "test_smoke.py"
            test_file.write_text(llm_tests, encoding="utf-8")
            checks.append("LLM-generated targeted tests written to tests/test_smoke.py")

        # ── Step 2: py_compile all Python files ──────────────────────────────
        for py_file in sorted(project_root.rglob("*.py")):
            rel = py_file.relative_to(project_root)
            try:
                py_compile.compile(str(py_file), doraise=True)
                checks.append(f"syntax ok: {rel}")
            except py_compile.PyCompileError as exc:
                msg = f"syntax error in {rel}: {exc.msg}"
                errors.append(msg)
                file_errors.setdefault(py_file.name, []).append(exc.msg)
                self.log.warning("syntax_error", file=str(rel), error=exc.msg)

        # ── Step 3: Required files present ───────────────────────────────────
        required = [
            "src/replicated_paper/model.py",
            "src/replicated_paper/inference.py",
            "src/replicated_paper/config.py",
            "src/replicated_paper/losses.py",
            "tests/test_smoke.py",
        ]
        for rel in required:
            if (project_root / rel).exists():
                checks.append(f"exists: {rel}")
            else:
                errors.append(f"missing required file: {rel}")

        # ── Step 4: Run pytest if no syntax errors ────────────────────────────
        if not errors:
            pytest_errors = self._run_pytest(project_root, venv_python=venv_python)
            if pytest_errors:
                errors.extend(pytest_errors)
                # Map pytest errors back to files for builder repair
                for pe in pytest_errors:
                    fname = self._guess_file(pe)
                    if fname:
                        file_errors.setdefault(fname, []).append(pe)
            else:
                checks.append("pytest: all tests passed")

        passed = len(errors) == 0
        self.log.info(
            "testing_complete",
            passed=passed,
            checks=len(checks),
            errors=len(errors),
            file_errors=list(file_errors.keys()),
        )
        return TestDiagnostics(passed=passed, checks=checks, errors=errors, file_errors=file_errors)

    # ------------------------------------------------------------------
    # LLM test generation
    # ------------------------------------------------------------------

    def _write_tests(self, src: Path, knowledge: KnowledgeBundle) -> str:
        """Read generated code files and ask LLM to write targeted tests."""
        model_code = self._safe_read(src / "model.py")
        inference_code = self._safe_read(src / "inference.py")
        config_code = self._safe_read(src / "config.py")

        if not model_code:
            return ""  # Nothing to test yet

        paper = knowledge.paper
        user = f"""\
Paper: {paper.metadata.title}
Architecture modules: {paper.architecture!r}
Loss functions: {paper.loss_functions!r}

--- model.py ---
{self._truncate(model_code, 3000)}

--- config.py ---
{self._truncate(config_code, 1000)}

--- inference.py ---
{self._truncate(inference_code, 2000)}

Write comprehensive pytest smoke tests for this implementation.
Tests must pass without GPU or data downloads.
Import path: from replicated_paper import InferenceRunner
             from replicated_paper.config import DEFAULT_CONFIG
             from replicated_paper.model import ReplicatedModel
             from replicated_paper.losses import compute_loss, LOSS_NAMES
"""
        try:
            code = self._ask_code(_SYS_TESTS, user)
            if code and "def test_" in code:
                return code
        except Exception as exc:
            self.log.warning("test_generation_failed", error=str(exc))
        return ""

    # ------------------------------------------------------------------
    # Pytest runner
    # ------------------------------------------------------------------

    def _run_pytest(self, project_root: Path, *, venv_python: Path | None = None) -> list[str]:
        """Run pytest in a subprocess.

        When ``venv_python`` is provided, uses the project's isolated venv
        (where torch/numpy are installed).  Falls back to ``sys.executable``.
        Returns list of error strings (empty = pass).
        """
        python = str(venv_python) if venv_python and venv_python.exists() else sys.executable
        try:
            src_dir = str(project_root / "src")
            result = subprocess.run(
                [python, "-m", "pytest", "tests/", "-v", "--tb=short", "-q"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=120,  # longer timeout when installing deps first time
                env={**__import__("os").environ, "PYTHONPATH": src_dir},
            )
            if result.returncode == 0:
                return []
            # Parse short failure summary
            failures: list[str] = []
            for line in (result.stdout + result.stderr).splitlines():
                if line.startswith("FAILED") or "Error" in line or "assert" in line.lower():
                    failures.append(line.strip())
            return failures[:20] if failures else [f"pytest exited {result.returncode}"]
        except subprocess.TimeoutExpired:
            return ["pytest timed out after 60s"]
        except Exception as exc:
            self.log.warning("pytest_run_failed", error=str(exc))
            return []  # Don't block on pytest runner issues

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8") if path.exists() else ""
        except Exception:
            return ""

    @staticmethod
    def _guess_file(error_line: str) -> str | None:
        """Guess which source file a pytest error relates to."""
        for name in ["model.py", "inference.py", "config.py", "losses.py", "preprocessing.py", "postprocessing.py"]:
            if name in error_line:
                return name
        return None
