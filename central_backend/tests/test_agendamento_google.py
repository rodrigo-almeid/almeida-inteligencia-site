"""Testes do módulo de agendamento: integração Google Calendar."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from backend.core.models import Appointment, AgendamentoConfig
from backend.agendamento.crypto import encrypt_key


class TestGoogleCalendarOAuth:
    def test_auth_url_sem_config_google(self, client, auth_headers, agendamento_config):
        with patch.dict("os.environ", {"GOOGLE_CLIENT_ID": "test-client-id"}):
            res = client.get("/agendamento/google/auth-url", headers=auth_headers)
            assert res.status_code == 200
            data = res.json()
            assert "url" in data
            assert "accounts.google.com" in data["url"]
            assert "test-client-id" in data["url"]

    def test_auth_url_sem_client_id(self, client, auth_headers, agendamento_config):
        with patch.dict("os.environ", {"GOOGLE_CLIENT_ID": ""}, clear=False):
            import os
            old = os.environ.pop("GOOGLE_CLIENT_ID", None)
            try:
                res = client.get("/agendamento/google/auth-url", headers=auth_headers)
                assert res.status_code == 500
            finally:
                if old:
                    os.environ["GOOGLE_CLIENT_ID"] = old

    def test_auth_url_sem_auth(self, client):
        res = client.get("/agendamento/google/auth-url")
        assert res.status_code == 401


class TestGoogleCalendarDisconnect:
    def test_disconnect_success(self, client, auth_headers, agendamento_config, db):
        agendamento_config.google_calendar_token = encrypt_key("fake-refresh-token")
        agendamento_config.google_calendar_id = "test@gmail.com"
        agendamento_config.google_calendar_ativo = True
        db.commit()

        with patch("backend.agendamento.routers.google_calendar.stop_watch_channel", new_callable=AsyncMock):
            res = client.post("/agendamento/google/disconnect", headers=auth_headers)
            assert res.status_code == 200

        db.refresh(agendamento_config)
        assert agendamento_config.google_calendar_token is None
        assert agendamento_config.google_calendar_ativo is False

    def test_disconnect_sem_config(self, client, auth_headers):
        res = client.post("/agendamento/google/disconnect", headers=auth_headers)
        assert res.status_code == 404


class TestGoogleCalendarWebhook:
    def test_webhook_valido(self, client, agendamento_config, db):
        agendamento_config.google_calendar_ativo = True
        agendamento_config.google_calendar_token = encrypt_key("fake-token")
        db.commit()

        res = client.post(
            "/agendamento/google/webhook",
            headers={
                "X-Goog-Channel-ID": "test-channel",
                "X-Goog-Channel-Token": f"config_{agendamento_config.id}",
            },
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_webhook_token_invalido(self, client):
        res = client.post(
            "/agendamento/google/webhook",
            headers={
                "X-Goog-Channel-ID": "test",
                "X-Goog-Channel-Token": "invalid",
            },
        )
        assert res.json()["status"] == "ignored"

    def test_webhook_config_inexistente(self, client):
        res = client.post(
            "/agendamento/google/webhook",
            headers={
                "X-Goog-Channel-ID": "test",
                "X-Goog-Channel-Token": "config_99999",
            },
        )
        assert res.json()["status"] == "config not found"


class TestGoogleSyncFunctions:
    @pytest.mark.asyncio
    async def test_criar_evento_google_desativado(self, db, agendamento_config, agendamento_appointment):
        """Se Google Calendar não está ativo, não faz nada."""
        from backend.agendamento.google_sync import criar_evento_google
        agendamento_config.google_calendar_ativo = False
        db.commit()

        await criar_evento_google(agendamento_config, agendamento_appointment, db)
        assert agendamento_appointment.google_event_id is None

    @pytest.mark.asyncio
    async def test_cancelar_evento_sem_event_id(self, db, agendamento_config, agendamento_appointment):
        """Se appointment não tem google_event_id, não faz nada."""
        from backend.agendamento.google_sync import cancelar_evento_google
        agendamento_config.google_calendar_ativo = True
        agendamento_config.google_calendar_token = encrypt_key("fake")
        agendamento_appointment.google_event_id = None
        db.commit()

        await cancelar_evento_google(agendamento_config, agendamento_appointment, db)

    @pytest.mark.asyncio
    async def test_criar_evento_google_mock(self, db, agendamento_config, agendamento_appointment):
        """Testa criação de evento com mock da API Google."""
        from backend.agendamento.google_sync import criar_evento_google

        agendamento_config.google_calendar_ativo = True
        agendamento_config.google_calendar_token = encrypt_key("fake-refresh")
        agendamento_config.google_calendar_id = "primary"
        db.commit()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "google-event-123"}

        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {"access_token": "fake-access-token"}

        with patch("backend.agendamento.google_sync.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(side_effect=[token_response, mock_response])
            mock_client.return_value = mock_instance

            await criar_evento_google(agendamento_config, agendamento_appointment, db)

        db.refresh(agendamento_appointment)
        assert agendamento_appointment.google_event_id == "google-event-123"


class TestConfigGoogleFields:
    def test_config_response_inclui_google(self, client, auth_headers, agendamento_config, db):
        agendamento_config.google_calendar_token = encrypt_key("test")
        agendamento_config.google_calendar_id = "user@gmail.com"
        agendamento_config.google_calendar_ativo = True
        db.commit()

        res = client.get("/agendamento/config", headers=auth_headers)
        assert res.status_code == 200, f"Response: {res.text}"
        data = res.json()
        assert data.get("google_calendar_conectado") is True
        assert data.get("google_calendar_ativo") is True
        assert data.get("google_calendar_id") == "user@gmail.com"

    def test_config_response_google_desconectado(self, client, auth_headers, agendamento_config):
        res = client.get("/agendamento/config", headers=auth_headers)
        assert res.status_code == 200, f"Response: {res.text}"
        data = res.json()
        assert data.get("google_calendar_conectado") is False
        assert data.get("google_calendar_ativo") is False
