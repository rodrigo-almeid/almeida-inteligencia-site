"""Testes unitários dos cron jobs de agendamento."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock
from backend.core.models import Appointment


class TestLimparPreReservasExpiradas:
    def test_expira_pre_reservas_vencidas(self, db, agendamento_config, agendamento_client, agendamento_servico):
        amanha = datetime.utcnow() + timedelta(days=1)
        appt = Appointment(
            data_hora=amanha, status="pre_reservado",
            expires_at=datetime.utcnow() - timedelta(minutes=10),
            config_id=agendamento_config.id, client_id=agendamento_client.id,
            service_id=agendamento_servico.id,
        )
        db.add(appt); db.commit(); db.refresh(appt)

        from backend.agendamento.cron import limpar_pre_reservas_expiradas
        limpar_pre_reservas_expiradas()

        db.expire_all()
        appt_atualizado = db.get(Appointment, appt.id)
        assert appt_atualizado.status == "expirado"

    def test_nao_expira_pre_reservas_validas(self, db, agendamento_config, agendamento_client, agendamento_servico):
        amanha = datetime.utcnow() + timedelta(days=1)
        appt = Appointment(
            data_hora=amanha, status="pre_reservado",
            expires_at=datetime.utcnow() + timedelta(minutes=3),
            config_id=agendamento_config.id, client_id=agendamento_client.id,
            service_id=agendamento_servico.id,
        )
        db.add(appt); db.commit(); db.refresh(appt)

        from backend.agendamento.cron import limpar_pre_reservas_expiradas
        limpar_pre_reservas_expiradas()

        db.expire_all()
        appt_atualizado = db.get(Appointment, appt.id)
        assert appt_atualizado.status == "pre_reservado"

    def test_nao_afeta_confirmados(self, db, agendamento_appointment):
        from backend.agendamento.cron import limpar_pre_reservas_expiradas
        limpar_pre_reservas_expiradas()

        db.expire_all()
        appt = db.get(Appointment, agendamento_appointment.id)
        assert appt.status == "confirmado"


class TestEnviarLembretes:
    """cron.py::enviar_lembretes usa backend.assistente.whatsapp (Meta Cloud API),
    compartilhado com o Assistente Virtual desde a fusão dos dois módulos."""

    def _criar_appointment(self, db, agendamento_config, agendamento_client, agendamento_servico, data_hora, lembrete_enviado=False):
        appt = Appointment(
            data_hora=data_hora, status="confirmado", lembrete_enviado=lembrete_enviado,
            config_id=agendamento_config.id, client_id=agendamento_client.id, service_id=agendamento_servico.id,
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)
        return appt

    def test_envia_lembrete_dentro_da_janela(self, db, agendamento_config, assistente_config, agendamento_client, agendamento_servico):
        appt = self._criar_appointment(
            db, agendamento_config, agendamento_client, agendamento_servico,
            datetime.utcnow() + timedelta(hours=1),
        )

        with patch("backend.agendamento.cron.enviar_mensagem", new=AsyncMock()) as mock_enviar:
            from backend.agendamento.cron import enviar_lembretes
            enviar_lembretes()

        mock_enviar.assert_called_once()
        db.expire_all()
        assert db.get(Appointment, appt.id).lembrete_enviado is True

    def test_nao_envia_fora_da_janela(self, db, agendamento_config, assistente_config, agendamento_client, agendamento_servico):
        appt = self._criar_appointment(
            db, agendamento_config, agendamento_client, agendamento_servico,
            datetime.utcnow() + timedelta(hours=5),
        )

        with patch("backend.agendamento.cron.enviar_mensagem", new=AsyncMock()) as mock_enviar:
            from backend.agendamento.cron import enviar_lembretes
            enviar_lembretes()

        mock_enviar.assert_not_called()
        db.expire_all()
        assert db.get(Appointment, appt.id).lembrete_enviado is False

    def test_nao_reenvia_se_ja_enviado(self, db, agendamento_config, assistente_config, agendamento_client, agendamento_servico):
        self._criar_appointment(
            db, agendamento_config, agendamento_client, agendamento_servico,
            datetime.utcnow() + timedelta(hours=1), lembrete_enviado=True,
        )

        with patch("backend.agendamento.cron.enviar_mensagem", new=AsyncMock()) as mock_enviar:
            from backend.agendamento.cron import enviar_lembretes
            enviar_lembretes()

        mock_enviar.assert_not_called()

    def test_pula_se_assistente_config_ausente(self, db, agendamento_config, agendamento_client, agendamento_servico):
        appt = self._criar_appointment(
            db, agendamento_config, agendamento_client, agendamento_servico,
            datetime.utcnow() + timedelta(hours=1),
        )

        with patch("backend.agendamento.cron.enviar_mensagem", new=AsyncMock()) as mock_enviar:
            from backend.agendamento.cron import enviar_lembretes
            enviar_lembretes()

        mock_enviar.assert_not_called()
        db.expire_all()
        assert db.get(Appointment, appt.id).lembrete_enviado is False
