"""Testes unitários dos cron jobs de agendamento."""
import pytest
from datetime import datetime, timedelta
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
