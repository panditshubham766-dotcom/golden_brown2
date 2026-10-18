"""Unit tests for OllamaNativeProvider."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest
from pydantic import BaseModel

from backend.app.model.ollama_native import DEFAULT_MODEL, OllamaNativeProvider
from backend.app.model.provider import ErrorLocalModelUnavailable, ErrorProcessing


class SampleAnswer(BaseModel):
    summary: str
    confidence: float


@pytest.fixture
def mock_tags_response():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [
            {"name": DEFAULT_MODEL, "model": f"{DEFAULT_MODEL}:latest"},
        ]
    }
    return mock_resp


def test_init_model_available(mock_tags_response):
    """Provider initialises cleanly when model is reported in /api/tags."""
    with patch("requests.get", return_value=mock_tags_response):
        provider = OllamaNativeProvider()
        assert provider.model == DEFAULT_MODEL


def test_init_model_unavailable():
    """Provider raises ErrorLocalModelUnavailable when model is absent."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"models": [{"name": "other-model:latest"}]}

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(ErrorLocalModelUnavailable):
            OllamaNativeProvider(model="gemma4:e2b-it-q4_K_M")


def test_init_connection_error():
    """Provider raises ErrorLocalModelUnavailable when Ollama is unreachable."""
    with patch("requests.get", side_effect=ConnectionRefusedError("Connection refused")):
        with pytest.raises(ErrorLocalModelUnavailable):
            OllamaNativeProvider()


def test_model_json_01(mock_tags_response):
    """T-MODEL-JSON-01: Verify schema-valid output is successfully parsed."""
    valid_obj = {"summary": "Rent is due on the 5th", "confidence": 0.95}

    mock_chat_resp = MagicMock()
    mock_chat_resp.status_code = 200
    mock_chat_resp.json.return_value = {
        "message": {"content": json.dumps(valid_obj)},
        "prompt_eval_count": 120,
        "eval_count": 50,
    }

    with patch("requests.get", return_value=mock_tags_response):
        provider = OllamaNativeProvider()

    with patch("requests.post", return_value=mock_chat_resp) as mock_post:
        result = provider.generate_structured(
            system_prompt="You are a legal assistant.",
            user_prompt="What is the rent due date?",
            response_schema=SampleAnswer,
        )

        assert isinstance(result, SampleAnswer)
        assert result.summary == "Rent is due on the 5th"
        assert result.confidence == 0.95
        assert mock_post.call_count == 1


def test_model_ctx_01(mock_tags_response):
    """T-MODEL-CTX-01: Assert context limit logic raises ErrorProcessing if tokens >= 8192."""
    mock_chat_resp = MagicMock()
    mock_chat_resp.status_code = 200
    mock_chat_resp.json.return_value = {
        "message": {"content": json.dumps({"summary": "test", "confidence": 1.0})},
        "prompt_eval_count": 8000,
        "eval_count": 200,  # 8000 + 200 = 8200 >= 8192
    }

    with patch("requests.get", return_value=mock_tags_response):
        provider = OllamaNativeProvider()

    with patch("requests.post", return_value=mock_chat_resp):
        with pytest.raises(ErrorProcessing, match="Context usage exceeded limit"):
            provider.generate_structured(
                system_prompt="system",
                user_prompt="user",
                response_schema=SampleAnswer,
            )


def test_model_notools_01(mock_tags_response):
    """T-MODEL-NOTOOLS-01: Assert the payload dictionary never contains the key 'tools'."""
    mock_chat_resp = MagicMock()
    mock_chat_resp.status_code = 200
    mock_chat_resp.json.return_value = {
        "message": {"content": json.dumps({"summary": "ok", "confidence": 0.8})},
        "prompt_eval_count": 10,
        "eval_count": 10,
    }

    with patch("requests.get", return_value=mock_tags_response):
        provider = OllamaNativeProvider()

    with patch("requests.post", return_value=mock_chat_resp) as mock_post:
        provider.generate_structured(
            system_prompt="sys",
            user_prompt="usr",
            response_schema=SampleAnswer,
        )

        call_args, call_kwargs = mock_post.call_args
        payload = call_kwargs.get("json", {})

        # Strict assertion: tools key must never exist
        assert "tools" not in payload
        assert payload.get("stream") is False
        assert payload.get("think") is False
        assert payload.get("options", {}).get("num_ctx") == 8192
        assert payload.get("options", {}).get("temperature") == 0


def test_priv_failclosed(mock_tags_response):
    """T-PRIV-FAILCLOSED: Assert completely mangled response fails closed and raises ErrorProcessing after single retry."""
    mangled_resp = MagicMock()
    mangled_resp.status_code = 200
    mangled_resp.json.return_value = {
        "message": {"content": "This is totally not JSON at all! {unclosed"},
        "prompt_eval_count": 50,
        "eval_count": 50,
    }

    with patch("requests.get", return_value=mock_tags_response):
        provider = OllamaNativeProvider()

    with patch("requests.post", return_value=mangled_resp) as mock_post:
        with pytest.raises(ErrorProcessing, match="Failed structured output validation after retry"):
            provider.generate_structured(
                system_prompt="sys",
                user_prompt="usr",
                response_schema=SampleAnswer,
            )

        # Assert exactly two attempts: initial + 1 single retry
        assert mock_post.call_count == 2


def test_retry_success(mock_tags_response):
    """Verify that if the first attempt fails validation, single retry can recover if valid."""
    bad_resp = MagicMock()
    bad_resp.status_code = 200
    bad_resp.json.return_value = {
        "message": {"content": "invalid json"},
        "prompt_eval_count": 20,
        "eval_count": 20,
    }

    good_resp = MagicMock()
    good_resp.status_code = 200
    good_resp.json.return_value = {
        "message": {"content": json.dumps({"summary": "Recovered", "confidence": 0.9})},
        "prompt_eval_count": 40,
        "eval_count": 30,
    }

    with patch("requests.get", return_value=mock_tags_response):
        provider = OllamaNativeProvider()

    with patch("requests.post", side_effect=[bad_resp, good_resp]) as mock_post:
        result = provider.generate_structured(
            system_prompt="sys",
            user_prompt="usr",
            response_schema=SampleAnswer,
        )
        assert result.summary == "Recovered"
        assert result.confidence == 0.9
        assert mock_post.call_count == 2
