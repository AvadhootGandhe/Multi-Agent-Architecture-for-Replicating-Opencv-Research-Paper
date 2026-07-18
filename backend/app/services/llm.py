from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

import structlog
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings

log = structlog.get_logger()

# Regex to strip Qwen3 thinking tokens from responses
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks emitted by Qwen3 before actual response."""
    return _THINK_RE.sub("", text).strip()


def _normalize_model(model: str) -> str:
    """Strip 'ollama/' prefix — ChatOllama expects bare model name."""
    if model.startswith("ollama/"):
        return model[len("ollama/"):]
    return model


def _to_lc_messages(messages: list[dict[str, str]]) -> list:
    """Convert OpenAI-style message dicts to LangChain message objects."""
    lc = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            lc.append(SystemMessage(content=content))
        else:
            lc.append(HumanMessage(content=content))
    return lc


class LLMClient:
    """
    LangChain ChatOllama adapter for Ollama-hosted models (default: qwen3:8b).

    - Strips Qwen3 <think> tokens from all responses.
    - Provides sync and async completion with exponential-backoff retry.
    - Provides extract_json() and extract_code() helpers for structured parsing.
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
        retries: int | None = None,
        on_llm_start: Any | None = None,
        on_llm_end: Any | None = None,
    ) -> None:
        raw_model = model or settings.llm_model
        self.model = _normalize_model(raw_model)
        self.base_url = base_url or settings.ollama_base_url
        self.timeout = timeout or settings.llm_timeout
        self.retries = retries or settings.llm_retries
        self.on_llm_start = on_llm_start
        self.on_llm_end = on_llm_end
        self._client = ChatOllama(
            model=self.model,
            base_url=self.base_url,
            timeout=self.timeout,
        )

    def _client_for(self, json_mode: bool, temperature: float) -> ChatOllama:
        """Return ChatOllama instance with correct format/temperature."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["format"] = "json"
        return ChatOllama(**kwargs)

    # ------------------------------------------------------------------
    # Sync completion (used by all agents — they run in thread pool)
    # ------------------------------------------------------------------

    def complete_sync(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
        agent_name: str | None = None,
    ) -> str:
        """Blocking LLM call with exponential-backoff retry."""
        if self.on_llm_start and agent_name:
            self.on_llm_start(agent_name)

        t0 = time.monotonic()
        client = self._client_for(json_mode, temperature)
        lc_messages = _to_lc_messages(messages)
        last_exc: Exception | None = None

        for attempt in range(1, self.retries + 1):
            try:
                response = client.invoke(lc_messages)
                raw = str(response.content or "")
                content = _strip_think(raw)
                log.debug(
                    "llm_complete",
                    model=self.model,
                    attempt=attempt,
                    input_chars=sum(len(m["content"]) for m in messages),
                    output_chars=len(content),
                )
                if self.on_llm_end and agent_name:
                    duration_ms = round((time.monotonic() - t0) * 1000)
                    self.on_llm_end(agent_name, duration_ms)
                return content
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                wait = 2**attempt
                log.warning("llm_retry", attempt=attempt, max=self.retries, error=str(exc), wait_s=wait)
                if attempt < self.retries:
                    time.sleep(wait)

        if self.on_llm_end and agent_name:
            duration_ms = round((time.monotonic() - t0) * 1000)
            self.on_llm_end(agent_name, duration_ms)
        raise RuntimeError(f"LLM call failed after {self.retries} attempts: {last_exc}") from last_exc

    # ------------------------------------------------------------------
    # Async completion (available for future async routes)
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> str:
        """Non-blocking LLM call with exponential-backoff retry."""
        client = self._client_for(json_mode, temperature)
        lc_messages = _to_lc_messages(messages)
        last_exc: Exception | None = None

        for attempt in range(1, self.retries + 1):
            try:
                response = await client.ainvoke(lc_messages)
                raw = str(response.content or "")
                return _strip_think(raw)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                wait = 2**attempt
                log.warning("llm_retry_async", attempt=attempt, error=str(exc))
                if attempt < self.retries:
                    await asyncio.sleep(wait)

        raise RuntimeError(f"LLM async call failed after {self.retries} attempts: {last_exc}") from last_exc

    # ------------------------------------------------------------------
    # Structured-output helpers
    # ------------------------------------------------------------------

    @staticmethod
    def extract_json(text: str) -> dict[str, Any]:
        """
        Parse JSON from LLM output.
        Tries: direct parse → markdown block → first {...} span → empty dict.
        """
        text = _strip_think(text).strip()

        # 1. Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. ```json ... ``` or ``` ... ```
        for pattern in [r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"]:
            m = re.search(pattern, text)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass

        # 3. First { ... } span (greedy)
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        log.warning("extract_json_failed", preview=text[:200])
        return {}

    @staticmethod
    def extract_code(text: str, language: str = "python") -> str:
        """
        Extract code from LLM output.
        Tries: language-specific block → any block → raw text.
        """
        text = _strip_think(text).strip()

        # language-specific block
        m = re.search(rf"```{re.escape(language)}\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()

        # generic block
        m = re.search(r"```\s*([\s\S]*?)\s*```", text)
        if m:
            return m.group(1).strip()

        # Return raw — likely the model returned plain code
        return text
