"""Testes dos adapters de tool-calling (backend/assistente/adapters/) — movidos
de backend/agendamento/adapters/ na fusão com o Assistente Virtual, sem cobertura
anterior nenhuma."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.assistente.adapters import gemini_adapter, groq_adapter, ollama_adapter
from backend.assistente.adapters.base import AGENDAMENTO_TOOLS_SCHEMA


def _mock_response(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


def _patch_client(module_path, response):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=response)
    return patch(module_path, return_value=mock_client)


class TestGeminiAdapter:
    @pytest.mark.asyncio
    async def test_call_retorna_texto_simples(self):
        resp = _mock_response(json_data={
            "candidates": [{"content": {"parts": [{"text": "Olá!"}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
        })
        with _patch_client("backend.assistente.adapters.gemini_adapter.httpx.AsyncClient", resp):
            result = await gemini_adapter.call([{"role": "user", "content": "oi"}], "system", "fake-key")
        assert result.content == "Olá!"
        assert result.tool_calls == []
        assert result.tokens_in == 10

    @pytest.mark.asyncio
    async def test_call_detecta_function_call(self):
        resp = _mock_response(json_data={
            "candidates": [{"content": {"parts": [
                {"functionCall": {"name": "buscar_horarios_disponiveis", "args": {"data": "2026-01-01", "service_id": 1}}}
            ]}}],
        })
        with _patch_client("backend.assistente.adapters.gemini_adapter.httpx.AsyncClient", resp):
            result = await gemini_adapter.call(
                [{"role": "user", "content": "quero agendar"}], "system", "fake-key",
                tools_schema=AGENDAMENTO_TOOLS_SCHEMA,
            )
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "buscar_horarios_disponiveis"
        assert result.tool_calls[0].arguments == {"data": "2026-01-01", "service_id": 1}

    @pytest.mark.asyncio
    async def test_call_erro_http(self):
        resp = _mock_response(status_code=400, text="chave inválida")
        with _patch_client("backend.assistente.adapters.gemini_adapter.httpx.AsyncClient", resp):
            result = await gemini_adapter.call([{"role": "user", "content": "oi"}], "system", "fake-key")
        assert result.error is not None
        assert "400" in result.error

    @pytest.mark.asyncio
    async def test_call_timeout(self):
        import httpx
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        with patch("backend.assistente.adapters.gemini_adapter.httpx.AsyncClient", return_value=mock_client):
            result = await gemini_adapter.call([{"role": "user", "content": "oi"}], "system", "fake-key")
        assert result.error == "Gemini timeout"


class TestGroqAdapter:
    @pytest.mark.asyncio
    async def test_call_retorna_texto_simples(self):
        resp = _mock_response(json_data={
            "choices": [{"message": {"content": "Olá!"}}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 3},
        })
        with _patch_client("backend.assistente.adapters.groq_adapter.httpx.AsyncClient", resp):
            result = await groq_adapter.call([{"role": "user", "content": "oi"}], "system", "fake-key")
        assert result.content == "Olá!"
        assert result.tokens_out == 3

    @pytest.mark.asyncio
    async def test_call_detecta_tool_calls_com_arguments_string(self):
        resp = _mock_response(json_data={
            "choices": [{"message": {
                "content": "",
                "tool_calls": [{"function": {"name": "registrar_gasto", "arguments": '{"descricao": "mercado", "valor": 50}'}}],
            }}],
        })
        with _patch_client("backend.assistente.adapters.groq_adapter.httpx.AsyncClient", resp):
            result = await groq_adapter.call([{"role": "user", "content": "gastei 50"}], "system", "fake-key")
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "registrar_gasto"
        assert result.tool_calls[0].arguments == {"descricao": "mercado", "valor": 50}

    @pytest.mark.asyncio
    async def test_call_erro_http(self):
        resp = _mock_response(status_code=401, text="unauthorized")
        with _patch_client("backend.assistente.adapters.groq_adapter.httpx.AsyncClient", resp):
            result = await groq_adapter.call([{"role": "user", "content": "oi"}], "system", "fake-key")
        assert result.error is not None


class TestOllamaAdapter:
    @pytest.mark.asyncio
    async def test_call_retorna_texto_simples(self):
        resp = _mock_response(json_data={
            "message": {"content": "Olá!"},
            "prompt_eval_count": 12,
            "eval_count": 4,
        })
        with _patch_client("backend.assistente.adapters.ollama_adapter.httpx.AsyncClient", resp):
            result = await ollama_adapter.call([{"role": "user", "content": "oi"}], "system", "http://localhost:11434", "llama3")
        assert result.content == "Olá!"
        assert result.model == "llama3"

    @pytest.mark.asyncio
    async def test_call_erro_http(self):
        resp = _mock_response(status_code=500, text="erro interno")
        with _patch_client("backend.assistente.adapters.ollama_adapter.httpx.AsyncClient", resp):
            result = await ollama_adapter.call([{"role": "user", "content": "oi"}], "system", "http://localhost:11434", "llama3")
        assert result.error is not None
