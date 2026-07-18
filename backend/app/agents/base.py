from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

import structlog

if TYPE_CHECKING:
    from app.services.llm import LLMClient

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class Agent(Protocol, Generic[InputT, OutputT]):
    """Structural protocol satisfied by any agent class."""

    name: str

    def run(self, payload: InputT) -> OutputT:
        ...


class LLMAgent(Generic[InputT, OutputT]):
    """
    Base class for all LLM-powered agents.

    Provides:
    - self.llm: LLMClient — pre-configured for Qwen3-8B / Ollama
    - self.log: structlog logger tagged with agent name
    - _ask(): single-call helper returning raw string
    - _ask_json(): call + JSON extraction with fallback dict
    - _ask_code(): call + code extraction
    """

    name: str = "base"

    def __init__(self, llm: LLMClient | None = None) -> None:
        if llm is None:
            from app.services.llm import LLMClient
            llm = LLMClient()
        self.llm = llm
        self.log = structlog.get_logger(agent=self.name)

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------

    def _ask(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> str:
        """Call LLM with system + user messages. Returns raw (think-stripped) string."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return self.llm.complete_sync(messages, json_mode=json_mode, temperature=temperature, agent_name=self.name)

    def _ask_json(
        self,
        system: str,
        user: str,
        fallback: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call LLM and parse JSON. Returns fallback dict on any failure."""
        try:
            raw = self._ask(system, user, json_mode=True)
            result = self.llm.extract_json(raw)
            if result:
                return result
        except Exception as exc:  # noqa: BLE001
            self.log.warning("ask_json_failed", error=str(exc))
        return fallback or {}

    def _ask_code(
        self,
        system: str,
        user: str,
        language: str = "python",
    ) -> str:
        """Call LLM and extract code block. Returns empty string on failure."""
        try:
            raw = self._ask(system, user, temperature=0.1)
            return self.llm.extract_code(raw, language)
        except Exception as exc:  # noqa: BLE001
            self.log.warning("ask_code_failed", error=str(exc))
        return ""

    def _truncate(self, text: str, max_chars: int = 6000) -> str:
        """Truncate long text to avoid exceeding context window."""
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return text[:half] + "\n\n...[truncated]...\n\n" + text[-half:]
