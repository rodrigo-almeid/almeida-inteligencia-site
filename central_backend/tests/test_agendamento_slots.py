"""Testes unitários da lógica de slots livres."""
import pytest
from datetime import date, datetime, timedelta
from backend.agendamento.slots import calcular_slots_livres, SLOT_GRANULARITY_MINUTES
from backend.core.models import Appointment, Service, HorarioFuncionamento


class TestSlotsLivres:
    def test_slots_basico(self, db, agendamento_config, agendamento_servico, agendamento_horarios):
        """Dia sem agendamentos deve retornar todos os slots possíveis."""
        amanha = date.today() + timedelta(days=1)
        if amanha.weekday() >= 6:
            amanha = amanha + timedelta(days=(7 - amanha.weekday()))
        slots = calcular_slots_livres(agendamento_config.id, agendamento_servico.id, amanha, db)
        assert len(slots) > 0
        assert "09:00" in slots

    def test_slots_domingo_fechado(self, db, agendamento_config, agendamento_servico, agendamento_horarios):
        """Domingo não tem horário de funcionamento → sem slots."""
        proximo_domingo = date.today()
        while proximo_domingo.weekday() != 6:
            proximo_domingo += timedelta(days=1)
        slots = calcular_slots_livres(agendamento_config.id, agendamento_servico.id, proximo_domingo, db)
        assert slots == []

    def test_slots_com_appointment_ocupado(self, db, agendamento_config, agendamento_servico, agendamento_horarios, agendamento_client):
        """Slot com agendamento confirmado não deve aparecer."""
        amanha = date.today() + timedelta(days=1)
        if amanha.weekday() >= 6:
            amanha = amanha + timedelta(days=(7 - amanha.weekday()))

        data_hora = datetime.combine(amanha, datetime.strptime("10:00", "%H:%M").time())
        appt = Appointment(
            data_hora=data_hora, status="confirmado",
            config_id=agendamento_config.id, client_id=agendamento_client.id,
            service_id=agendamento_servico.id,
        )
        db.add(appt); db.commit()

        slots = calcular_slots_livres(agendamento_config.id, agendamento_servico.id, amanha, db)
        assert "10:00" not in slots

    def test_slots_pre_reserva_expirada_libera(self, db, agendamento_config, agendamento_servico, agendamento_horarios, agendamento_client):
        """Pré-reserva expirada deve liberar o slot."""
        amanha = date.today() + timedelta(days=1)
        if amanha.weekday() >= 6:
            amanha = amanha + timedelta(days=(7 - amanha.weekday()))

        data_hora = datetime.combine(amanha, datetime.strptime("11:00", "%H:%M").time())
        appt = Appointment(
            data_hora=data_hora, status="pre_reservado",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
            config_id=agendamento_config.id, client_id=agendamento_client.id,
            service_id=agendamento_servico.id,
        )
        db.add(appt); db.commit()

        slots = calcular_slots_livres(agendamento_config.id, agendamento_servico.id, amanha, db)
        assert "11:00" in slots

    def test_slots_servico_longo_adjacencia(self, db, agendamento_config, agendamento_horarios, agendamento_client):
        """Serviço de 60min deve verificar 2 slots consecutivos de 30min."""
        servico_longo = Service(
            nome="Progressiva", duracao_minutos=60, preco=150.0,
            ativo=True, config_id=agendamento_config.id,
        )
        db.add(servico_longo); db.commit(); db.refresh(servico_longo)

        amanha = date.today() + timedelta(days=1)
        if amanha.weekday() >= 6:
            amanha = amanha + timedelta(days=(7 - amanha.weekday()))

        slots = calcular_slots_livres(agendamento_config.id, servico_longo.id, amanha, db)
        assert len(slots) > 0
        assert "17:30" not in slots

    def test_slots_servico_inexistente(self, db, agendamento_config, agendamento_horarios):
        amanha = date.today() + timedelta(days=1)
        slots = calcular_slots_livres(agendamento_config.id, 99999, amanha, db)
        assert slots == []

    def test_slots_nao_ultrapassa_horario_fim(self, db, agendamento_config, agendamento_horarios):
        """Serviço de 90min: 16:30+90min=18:00 é válido, mas 17:00+90min=18:30 ultrapassa."""
        servico_90 = Service(
            nome="Super Longo", duracao_minutos=90, preco=200.0,
            ativo=True, config_id=agendamento_config.id,
        )
        db.add(servico_90); db.commit(); db.refresh(servico_90)

        amanha = date.today() + timedelta(days=1)
        if amanha.weekday() >= 6:
            amanha = amanha + timedelta(days=(7 - amanha.weekday()))

        slots = calcular_slots_livres(agendamento_config.id, servico_90.id, amanha, db)
        assert "17:00" not in slots
        assert "17:30" not in slots
        assert "16:30" in slots
