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


class TestGoogleCalendarCallback:
    """POST-fusão: o callback precisa funcionar mesmo se o usuário nunca
    salvou a aba de catálogo/negócio antes (sem AgendamentoConfig prévia) —
    regressão do bug real encontrado em produção (config_not_found)."""

    def _mock_google_http(self, mock_client_cls):
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {"access_token": "fake-access", "refresh_token": "fake-refresh"}

        cal_response = MagicMock()
        cal_response.status_code = 200
        cal_response.json.return_value = {"id": "dono@gmail.com"}

        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post = AsyncMock(return_value=token_response)
        mock_instance.get = AsyncMock(return_value=cal_response)
        mock_client_cls.return_value = mock_instance

    def test_callback_cria_config_automaticamente_se_nao_existir(self, client, user, db):
        assert db.query(AgendamentoConfig).filter(AgendamentoConfig.user_id == user.id).first() is None
        state = encrypt_key(str(user.id))

        with patch("backend.agendamento.routers.google_calendar.httpx.AsyncClient") as mock_client_cls, \
             patch("backend.agendamento.routers.google_calendar.setup_watch_channel", new_callable=AsyncMock):
            self._mock_google_http(mock_client_cls)
            res = client.get(
                f"/agendamento/google/callback?code=fake-code&state={state}",
                follow_redirects=False,
            )

        assert res.status_code in (302, 307)
        assert "google=ok" in res.headers["location"]

        config = db.query(AgendamentoConfig).filter(AgendamentoConfig.user_id == user.id).first()
        assert config is not None
        assert config.google_calendar_ativo is True
        assert config.google_calendar_id == "dono@gmail.com"

    def test_callback_atualiza_config_existente(self, client, user, agendamento_config, db):
        state = encrypt_key(str(user.id))

        with patch("backend.agendamento.routers.google_calendar.httpx.AsyncClient") as mock_client_cls, \
             patch("backend.agendamento.routers.google_calendar.setup_watch_channel", new_callable=AsyncMock):
            self._mock_google_http(mock_client_cls)
            res = client.get(
                f"/agendamento/google/callback?code=fake-code&state={state}",
                follow_redirects=False,
            )

        assert res.status_code in (302, 307)
        assert "google=ok" in res.headers["location"]

        total = db.query(AgendamentoConfig).filter(AgendamentoConfig.user_id == user.id).count()
        assert total == 1  # não duplica a config já existente
        db.refresh(agendamento_config)
        assert agendamento_config.google_calendar_ativo is True

    def test_callback_com_erro_do_google_redireciona(self, client):
        res = client.get("/agendamento/google/callback?error=access_denied", follow_redirects=False)
        assert res.status_code in (302, 307)
        assert "google=error" in res.headers["location"]

    def test_callback_sem_code_redireciona(self, client):
        res = client.get("/agendamento/google/callback", follow_redirects=False)
        assert res.status_code in (302, 307)
        assert "missing_params" in res.headers["location"]

    def test_callback_state_invalido_redireciona(self, client):
        res = client.get("/agendamento/google/callback?code=x&state=lixo-invalido", follow_redirects=False)
        assert res.status_code in (302, 307)
        assert "invalid_state" in res.headers["location"]


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

    @pytest.mark.asyncio
    async def test_criar_evento_nao_mistura_utc_com_timezone_nomeado(self, db, agendamento_config, agendamento_appointment):
        """Regressão de bug real de fuso: mandar 'Z' (UTC) junto com
        timeZone: America/Sao_Paulo faz o Google reinterpretar o horário
        errado — data_hora é sempre horário local, sem sufixo Z."""
        from backend.agendamento.google_sync import criar_evento_google

        agendamento_config.google_calendar_ativo = True
        agendamento_config.google_calendar_token = encrypt_key("fake-refresh")
        agendamento_config.google_calendar_id = "primary"
        db.commit()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "google-event-456"}
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

            evento_enviado = mock_instance.post.call_args_list[1].kwargs["json"]

        assert not evento_enviado["start"]["dateTime"].endswith("Z")
        assert evento_enviado["start"]["timeZone"] == "America/Sao_Paulo"
        assert evento_enviado["start"]["dateTime"] == agendamento_appointment.data_hora.isoformat()


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
