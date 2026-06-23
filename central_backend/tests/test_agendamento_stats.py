"""Testes do módulo de agendamento: /agendamento/stats."""
import pytest


class TestStats:
    def test_stats_success(self, client, auth_headers, agendamento_config):
        res = client.get("/agendamento/stats", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert "conversas_hoje" in data
        assert "agendamentos_confirmados_hoje" in data
        assert "total_agendamentos_mes" in data
        assert "ultima_llm_usada" in data
        assert "proximos_agendamentos" in data

    def test_stats_com_agendamento(self, client, auth_headers, agendamento_appointment):
        res = client.get("/agendamento/stats", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["proximos_agendamentos"]) >= 1

    def test_stats_sem_config(self, client, auth_headers):
        res = client.get("/agendamento/stats", headers=auth_headers)
        assert res.status_code == 404

    def test_stats_sem_auth(self, client):
        res = client.get("/agendamento/stats")
        assert res.status_code == 401

    def test_stats_llm_nula_sem_logs(self, client, auth_headers, agendamento_config):
        res = client.get("/agendamento/stats", headers=auth_headers)
        assert res.json()["ultima_llm_usada"] is None

    def test_stats_com_llm_log(self, client, auth_headers, agendamento_config, db):
        from backend.core.models import LlmLog
        log = LlmLog(
            provider="gemini", model="gemini-2.0-flash", status_code=200,
            tokens_in=100, tokens_out=50, latency_ms=800,
            config_id=agendamento_config.id,
        )
        db.add(log); db.commit()
        res = client.get("/agendamento/stats", headers=auth_headers)
        assert res.json()["ultima_llm_usada"] == "gemini"
