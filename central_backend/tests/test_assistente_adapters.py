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

    @pytest.mark.asyncio
    async def test_call_extrai_tool_call_escrita_como_texto(self):
        """Regressão de bug real: llama-3.1-8b-instant às vezes escreve a
        chamada de função como texto pseudo-XML em vez de usar tool_calls
        estruturado — o texto ao redor (alegação não verificada) precisa ser
        descartado, e a chamada precisa ser executada de verdade."""
        conteudo = (
            'Você já tem um compromisso marcado com o dentista hoje às 14h. '
            '<function=marcar_compromisso>{"data_hora": "2026-07-10 14:00", "service_id": 1}</function>'
        )
        resp = _mock_response(json_data={
            "choices": [{"message": {"content": conteudo}}],
        })
        with _patch_client("backend.assistente.adapters.groq_adapter.httpx.AsyncClient", resp):
            result = await groq_adapter.call([{"role": "user", "content": "marca dentista às 14"}], "system", "fake-key")

        assert result.content == ""  # descarta a alegação não verificada, não só a tag
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "marcar_compromisso"
        assert result.tool_calls[0].arguments == {"data_hora": "2026-07-10 14:00", "service_id": 1}


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


class TestExtrairToolCallsDeTexto:
    """backend/assistente/adapters/base.py::extrair_tool_calls_de_texto"""

    def test_sem_padrao_retorna_conteudo_original(self):
        from backend.assistente.adapters.base import extrair_tool_calls_de_texto
        texto, calls = extrair_tool_calls_de_texto("Olá! Como posso ajudar?")
        assert texto == "Olá! Como posso ajudar?"
        assert calls == []

    def test_conteudo_vazio_nao_quebra(self):
        from backend.assistente.adapters.base import extrair_tool_calls_de_texto
        texto, calls = extrair_tool_calls_de_texto("")
        assert texto == ""
        assert calls == []

    def test_extrai_e_descarta_texto_ao_redor(self):
        from backend.assistente.adapters.base import extrair_tool_calls_de_texto
        conteudo = 'Já tem algo marcado! <function=cancelar_agendamento>{}</function>'
        texto, calls = extrair_tool_calls_de_texto(conteudo)
        assert texto == ""
        assert len(calls) == 1
        assert calls[0].name == "cancelar_agendamento"
        assert calls[0].arguments == {}

    def test_multiplas_chamadas_no_mesmo_texto(self):
        from backend.assistente.adapters.base import extrair_tool_calls_de_texto
        conteudo = (
            '<function=buscar_horarios_disponiveis>{"data": "2026-07-10", "service_id": 1}</function>'
            '<function=consultar_agenda>{}</function>'
        )
        texto, calls = extrair_tool_calls_de_texto(conteudo)
        assert len(calls) == 2
        assert calls[0].name == "buscar_horarios_disponiveis"
        assert calls[1].name == "consultar_agenda"

    def test_json_invalido_na_chamada_nao_quebra(self):
        from backend.assistente.adapters.base import extrair_tool_calls_de_texto
        conteudo = '<function=marcar_compromisso>{invalido}</function>'
        texto, calls = extrair_tool_calls_de_texto(conteudo)
        assert len(calls) == 1
        assert calls[0].arguments == {}
