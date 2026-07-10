"""Testes do orquestrador único de tool-calling (backend/assistente/llm_gateway.py)
— cérebro da fusão Agendamento + Assistente Virtual. Os adapters são mockados
(sem chamada HTTP real); a execução das tools roda de verdade contra o banco de
teste, igual ao comportamento em produção."""
import json
import pytest
from unittest.mock import AsyncMock, patch

from backend.core.models import Conta, CompraSupermercado, AssistenteConfig
from backend.assistente.adapters.base import LlmResponse, ToolCall
from backend.assistente import llm_gateway


def _resp(content="", tool_calls=None, error=None):
    return LlmResponse(content=content, tool_calls=tool_calls or [], error=error, model="gemini-2.0-flash")


class TestProcessarMensagemAgendamento:
    @pytest.mark.asyncio
    async def test_llm_chama_tool_de_agendamento(self, db, user, assistente_config, agendamento_config, agendamento_servico, agendamento_horarios):
        agendamento_config.ativo = True
        db.commit()

        dia_semana = agendamento_horarios[0].dia_semana
        from datetime import date, timedelta
        d = date.today()
        while d.weekday() != dia_semana:
            d += timedelta(days=1)

        primeira = _resp(tool_calls=[
            ToolCall(name="buscar_horarios_disponiveis", arguments={"data": d.isoformat(), "service_id": agendamento_servico.id}),
        ])
        segunda = _resp(content="Aqui estão os horários disponíveis!")

        with patch("backend.assistente.llm_gateway.gemini_adapter.call", new=AsyncMock(side_effect=[primeira, segunda])):
            resposta = await llm_gateway.processar_mensagem("quero agendar um horário", assistente_config, user, db)

        assert resposta == "Aqui estão os horários disponíveis!"

    @pytest.mark.asyncio
    async def test_llm_chama_consultar_agenda_nao_alucina(self, db, user, assistente_config, agendamento_config, agendamento_client, agendamento_servico):
        """Mesma regressão de test_assistente.py::TestConsultarAgendaSemAlucinacao,
        agora pelo pipeline de tool-calling: a tool sempre reflete Appointment real."""
        from backend.core.models import Appointment
        from datetime import datetime, timedelta

        agendamento_config.ativo = True
        assistente_config.numero_autorizado = agendamento_client.telefone
        db.commit()
        amanha = datetime.utcnow() + timedelta(days=1)
        db.add(Appointment(
            data_hora=amanha, status="confirmado",
            config_id=agendamento_config.id, client_id=agendamento_client.id, service_id=agendamento_servico.id,
        ))
        db.commit()

        primeira = _resp(tool_calls=[ToolCall(name="consultar_agenda", arguments={})])
        segunda = _resp(content="Você tem Corte Masculino confirmado amanhã!")

        with patch("backend.assistente.llm_gateway.gemini_adapter.call", new=AsyncMock(side_effect=[primeira, segunda])) as mock_call:
            resposta = await llm_gateway.processar_mensagem("tenho algo marcado?", assistente_config, user, db)

        assert resposta == "Você tem Corte Masculino confirmado amanhã!"
        # confirma que o resultado real da tool (não um texto genérico) foi passado pro LLM na 2ª chamada
        segunda_chamada_messages = mock_call.call_args_list[1].args[0]
        resultado_tool = segunda_chamada_messages[-1]["content"]
        assert "Corte Masculino" in resultado_tool

    @pytest.mark.asyncio
    async def test_tools_de_agendamento_somem_quando_modulo_inativo(self, db, user, assistente_config, agendamento_config):
        agendamento_config.ativo = False
        db.commit()

        chamada = _resp(content="Olá!")
        with patch("backend.assistente.llm_gateway.gemini_adapter.call", new=AsyncMock(return_value=chamada)) as mock_call:
            await llm_gateway.processar_mensagem("oi", assistente_config, user, db)

        tools_schema = mock_call.call_args.args[3] if len(mock_call.call_args.args) > 3 else mock_call.call_args.kwargs.get("tools_schema")
        nomes = {t["name"] for t in tools_schema}
        assert "buscar_horarios_disponiveis" not in nomes
        assert "registrar_gasto" in nomes


class TestProcessarMensagemFinanceiro:
    @pytest.mark.asyncio
    async def test_llm_chama_registrar_gasto_completo(self, db, user, assistente_config):
        primeira = _resp(tool_calls=[
            ToolCall(name="registrar_gasto", arguments={"descricao": "mercado", "valor": 50, "forma_pagamento": "debito"}),
        ])
        segunda = _resp(content="Registrado!")

        with patch("backend.assistente.llm_gateway.gemini_adapter.call", new=AsyncMock(side_effect=[primeira, segunda])):
            resposta = await llm_gateway.processar_mensagem("gastei 50 no mercado", assistente_config, user, db)

        assert resposta == "Registrado!"
        conta = db.query(Conta).filter(Conta.user_id == user.id, Conta.descricao == "mercado").first()
        assert conta is not None
        assert conta.valor == 50

    @pytest.mark.asyncio
    async def test_registrar_gasto_incompleto_nao_salva(self, db, user, assistente_config):
        primeira = _resp(tool_calls=[
            ToolCall(name="registrar_gasto", arguments={"descricao": "mercado"}),
        ])
        segunda = _resp(content="Faltou me dizer o valor e a forma de pagamento!")

        with patch("backend.assistente.llm_gateway.gemini_adapter.call", new=AsyncMock(side_effect=[primeira, segunda])):
            await llm_gateway.processar_mensagem("gastei no mercado", assistente_config, user, db)

        assert db.query(Conta).filter(Conta.user_id == user.id).count() == 0

    @pytest.mark.asyncio
    async def test_llm_chama_consultar_financas(self, db, user, assistente_config):
        primeira = _resp(tool_calls=[ToolCall(name="consultar_financas", arguments={})])
        segunda = _resp(content="Seu saldo está positivo!")

        with patch("backend.assistente.llm_gateway.gemini_adapter.call", new=AsyncMock(side_effect=[primeira, segunda])):
            resposta = await llm_gateway.processar_mensagem("como estão minhas finanças?", assistente_config, user, db)

        assert resposta == "Seu saldo está positivo!"


class TestSystemPromptComServicoSemPreco:
    @pytest.mark.asyncio
    async def test_nao_quebra_quando_servico_nao_tem_preco(self, db, user, assistente_config, agendamento_config):
        """Regressão: agenda pessoal (reunião, compromisso) normalmente não tem
        preço — Service.preco=None não pode derrubar a montagem do system prompt."""
        from backend.core.models import Service
        agendamento_config.ativo = True
        db.add(Service(nome="Reunião", duracao_minutos=60, preco=None, ativo=True, config_id=agendamento_config.id))
        db.commit()

        chamada = _resp(content="Oi! Como posso ajudar?")
        with patch("backend.assistente.llm_gateway.gemini_adapter.call", new=AsyncMock(return_value=chamada)):
            resposta = await llm_gateway.processar_mensagem("oi", assistente_config, user, db)

        assert resposta == "Oi! Como posso ajudar?"


class TestFallbackEntreProviders:
    @pytest.mark.asyncio
    async def test_fallback_para_proximo_provider_em_erro(self, db, user):
        config = AssistenteConfig(
            user_id=user.id,
            evolution_url="http://evolution:8080", evolution_api_key="k", evolution_instance="i",
            numero_autorizado="5543999211099", webhook_secret="s",
            provedores_llm=json.dumps([
                {"tipo": "gemini", "api_key": "chave-gemini", "ativo": True},
                {"tipo": "groq", "api_key": "chave-groq", "ativo": True},
            ]),
            ativo=True, usar_tool_calling=True,
        )
        db.add(config)
        db.commit()
        db.refresh(config)

        gemini_falha = _resp(error="Gemini HTTP 500: erro")
        groq_sucesso = _resp(content="Oi! Tudo certo por aqui.")

        with patch("backend.assistente.llm_gateway.gemini_adapter.call", new=AsyncMock(return_value=gemini_falha)), \
             patch("backend.assistente.llm_gateway.groq_adapter.call", new=AsyncMock(return_value=groq_sucesso)) as mock_groq:
            resposta = await llm_gateway.processar_mensagem("oi", config, user, db)

        assert resposta == "Oi! Tudo certo por aqui."
        mock_groq.assert_called_once()
