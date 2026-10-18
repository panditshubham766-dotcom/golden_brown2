"""Ollama native API provider implementation for structured local LLM generation."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Type, TypeVar
import requests
from pydantic import BaseModel, ValidationError

from backend.app.model.provider import ErrorLocalModelUnavailable, ErrorProcessing, LLMProvider

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "gemma4:e2b-it-q4_K_M"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
CONTEXT_LIMIT = 8192


def _match_model(name: str, target: str) -> bool:
    if name == target:
        return True
    if f"{name}:latest" == target or name == f"{target}:latest":
        return True
    return False


class OllamaNativeProvider(LLMProvider):
    """Local LLM provider interfacing directly with Ollama's native HTTP API."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._verify_model()

    def _verify_model(self) -> None:
        """Verify that Ollama is running and the specified model is present locally."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=self.timeout)
            if resp.status_code != 200:
                raise ErrorLocalModelUnavailable(
                    f"Ollama returned HTTP {resp.status_code} while fetching tags"
                )
            data = resp.json()
        except Exception as exc:
            if isinstance(exc, ErrorLocalModelUnavailable):
                raise
            raise ErrorLocalModelUnavailable(
                f"Cannot connect to Ollama at {self.base_url}: {exc}"
            ) from exc

        models: List[Dict[str, Any]] = data.get("models", [])
        available_names: List[str] = []
        for m in models:
            if isinstance(m, dict):
                if name := m.get("name"):
                    available_names.append(name)
                if alias := m.get("model"):
                    available_names.append(alias)

        if not any(_match_model(name, self.model) for name in available_names):
            raise ErrorLocalModelUnavailable(
                f"Model '{self.model}' not found in local Ollama instance. Available: {available_names}"
            )

    def _check_context_usage(self, response_data: Dict[str, Any]) -> None:
        """Raise ErrorProcessing if prompt + completion tokens reach or exceed context limit."""
        prompt_eval = response_data.get("prompt_eval_count") or 0
        eval_count = response_data.get("eval_count") or 0
        total_tokens = prompt_eval + eval_count
        if total_tokens >= CONTEXT_LIMIT:
            raise ErrorProcessing(
                f"Context usage exceeded limit: {total_tokens} >= {CONTEXT_LIMIT} tokens"
            )

    def _execute_chat_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send chat request to Ollama with strict payload constraints."""
        # CRITICAL constraint: never include tools key
        if "tools" in payload:
            del payload["tools"]
        assert "tools" not in payload, "CRITICAL: 'tools' key must never be included in Ollama payload"

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ErrorProcessing(f"Failed to communicate with Ollama: {exc}") from exc

        if resp.status_code != 200:
            raise ErrorProcessing(
                f"Ollama chat endpoint returned HTTP {resp.status_code}: {resp.text}"
            )

        try:
            data = resp.json()
        except Exception as exc:
            raise ErrorProcessing(f"Malformed JSON response from Ollama: {exc}") from exc

        self._check_context_usage(data)
        return data

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Type[T],
    ) -> T:
        """
        Generate structured output validated against response_schema.
        Enforces a single retry on validation error before failing closed.
        """
        schema_json = response_schema.model_json_schema()

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "format": schema_json,
            "options": {
                "temperature": 0,
                "seed": 42,
                "num_ctx": CONTEXT_LIMIT,
            },
        }

        # Attempt 1
        data = self._execute_chat_request(payload)
        content = data.get("message", {}).get("content", "")

        last_error = ""
        try:
            return response_schema.model_validate_json(content)
        except (ValidationError, ValueError, TypeError) as first_err:
            last_error = str(first_err)
            logger.warning("First validation attempt failed: %s. Retrying once.", last_error)

        # Single format-retry
        retry_messages = list(messages)
        retry_messages.append({"role": "assistant", "content": content})
        retry_messages.append(
            {
                "role": "user",
                "content": (
                    f"The previous output failed schema validation: {last_error}\n"
                    f"Please fix the formatting and output only valid JSON matching the schema."
                ),
            }
        )

        retry_payload: Dict[str, Any] = {
            "model": self.model,
            "messages": retry_messages,
            "stream": False,
            "think": False,
            "format": schema_json,
            "options": {
                "temperature": 0,
                "seed": 42,
                "num_ctx": CONTEXT_LIMIT,
            },
        }

        retry_data = self._execute_chat_request(retry_payload)
        retry_content = retry_data.get("message", {}).get("content", "")

        try:
            return response_schema.model_validate_json(retry_content)
        except (ValidationError, ValueError, TypeError) as second_err:
            logger.error("Second validation attempt failed: %s. Failing closed.", second_err)
            raise ErrorProcessing(
                f"Failed structured output validation after retry: {second_err}"
            ) from second_err
