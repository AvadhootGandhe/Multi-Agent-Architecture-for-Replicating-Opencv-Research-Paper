"""Per-run virtual environment manager.

Each research paper replication run gets its own isolated Python venv inside
``generated/<run_id>/project/venv/``.  After the builder generates code and
``requirements.txt``, the orchestrator calls this service to:

1. Create a fresh venv
2. Install the project's requirements (CPU-only torch by default)
3. Provide the venv's Python path for the tester to run pytest in isolation
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

import structlog

log = structlog.get_logger()

# CPU-only torch index — ~200 MB instead of ~2 GB
_CPU_TORCH_INDEX = "https://download.pytorch.org/whl/cpu"


class VenvManager:
    """Create and manage per-run virtual environments."""

    @staticmethod
    def venv_dir(project_dir: Path) -> Path:
        """Return the venv directory path for a project."""
        return project_dir / "venv"

    @staticmethod
    def get_python_path(project_dir: Path) -> Path:
        """Return the Python executable inside the project's venv (cross-platform)."""
        venv = VenvManager.venv_dir(project_dir)
        if platform.system() == "Windows":
            return venv / "Scripts" / "python.exe"
        return venv / "bin" / "python"

    @staticmethod
    def get_pip_path(project_dir: Path) -> Path:
        """Return the pip executable inside the project's venv (cross-platform)."""
        venv = VenvManager.venv_dir(project_dir)
        if platform.system() == "Windows":
            return venv / "Scripts" / "pip.exe"
        return venv / "bin" / "pip"

    @classmethod
    def create_venv(cls, project_dir: Path) -> Path:
        """Create a virtual environment inside ``project_dir/venv/``.

        Returns the path to the venv directory.
        Skips creation if the venv already exists and has a valid Python.
        """
        venv_path = cls.venv_dir(project_dir)
        python_path = cls.get_python_path(project_dir)

        if python_path.exists():
            log.info("venv_exists", venv=str(venv_path))
            return venv_path

        log.info("venv_creating", venv=str(venv_path))
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            log.info("venv_created", venv=str(venv_path))
        except subprocess.CalledProcessError as exc:
            log.error("venv_create_failed", stderr=exc.stderr[:500])
            raise RuntimeError(f"Failed to create venv: {exc.stderr[:300]}") from exc
        except subprocess.TimeoutExpired:
            raise RuntimeError("Venv creation timed out after 120s")

        return venv_path

    @classmethod
    def install_requirements(cls, project_dir: Path) -> bool:
        """Install ``requirements.txt`` into the project's venv.

        Uses CPU-only PyTorch index to keep installs fast and small.
        Returns True on success, False on failure (non-fatal — tests may
        still pass on syntax alone).
        """
        req_file = project_dir / "requirements.txt"
        if not req_file.exists():
            log.warning("venv_no_requirements", project=str(project_dir))
            return False

        pip_path = cls.get_pip_path(project_dir)
        if not pip_path.exists():
            log.error("venv_pip_missing", pip=str(pip_path))
            return False

        log.info("venv_installing_deps", requirements=str(req_file))
        try:
            # Upgrade pip first (silently)
            subprocess.run(
                [str(pip_path), "install", "--upgrade", "pip"],
                capture_output=True,
                text=True,
                timeout=120,
            )

            # Install requirements with CPU-only torch index
            result = subprocess.run(
                [
                    str(pip_path), "install",
                    "-r", str(req_file),
                    "--extra-index-url", _CPU_TORCH_INDEX,
                    "--no-cache-dir",
                ],
                capture_output=True,
                text=True,
                timeout=600,  # torch install can be slow
            )
            if result.returncode == 0:
                log.info("venv_deps_installed")
                return True
            else:
                log.warning(
                    "venv_deps_failed",
                    returncode=result.returncode,
                    stderr=result.stderr[:500],
                )
                return False
        except subprocess.TimeoutExpired:
            log.warning("venv_deps_timeout")
            return False
        except Exception as exc:
            log.warning("venv_deps_error", error=str(exc))
            return False

    @classmethod
    def run_in_venv(
        cls,
        project_dir: Path,
        args: list[str],
        *,
        timeout: int = 120,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a command using the venv's Python.

        ``args`` should start with module flags, e.g. ``["-m", "pytest", ...]``.
        The venv Python is prepended automatically.
        """
        python = cls.get_python_path(project_dir)
        if not python.exists():
            raise RuntimeError(f"Venv Python not found at {python}")

        env = {**os.environ, **(extra_env or {})}
        # Set PYTHONPATH so the generated src/ is importable
        src_dir = str(project_dir / "src")
        env["PYTHONPATH"] = src_dir

        return subprocess.run(
            [str(python)] + args,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
