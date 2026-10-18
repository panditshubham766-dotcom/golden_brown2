"""LLM provider abstract interface and exceptions."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ErrorLocalModelUnavailable(Exception):
    """Raised when the required local model cannot be found or reached in Ollama."""


class ErrorProcessing(Exception):
    """Raised when generation, validation, or context limits fail."""


class LLMProvider(ABC):
    """Narrow interface for local structured LLM generation."""

    @abstractmethod
    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Type[T],
    ) -> T:
        """Generate structured output validated against response_schema."""
