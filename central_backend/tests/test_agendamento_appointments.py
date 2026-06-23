"""Testes do módulo de agendamento: /agendamento/appointments."""
import pytest
from datetime import datetime, timedelta


class TestListarAppointments:
    def test_listar_por_data(self, client, auth_headers, agendamento_appointment):
        data = agendamento_appointment.data_hora.strftime("%Y-%m-%d")
        res = client.get(f"/agendamento/appointments?data={data}", headers=auth_headers)
        assert res.status_code == 200
        ids = [a["id"] for a in res.json()]
        assert agendamento_appointment.id in ids

    def test_listar_por_status(self, client, auth_headers, agendamento_appointment):
        data = agendamento_appointment.data_hora.strftime("%Y-%m-%d")
        res = client.get(f"/agendamento/appointments?data={data}&status=confirmado", headers=auth_headers)
        assert res.status_code == 200
        assert all(a["status"] == "confirmado" for a in res.json())

    def test_listar_filtro_status_vazio(self, client, auth_headers, agendamento_appointment):
        data = agendamento_appointment.data_hora.strftime("%Y-%m-%d")
        res = client.get(f"/agendamento/appointments?data={data}&status=cancelado", headers=auth_headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_listar_sem_config(self, client, auth_headers):
        res = client.get("/agendamento/appointments", headers=auth_headers)
        assert res.status_code == 404

    def test_listar_sem_auth(self, client):
        res = client.get("/agendamento/appointments")
        assert res.status_code == 401

    def test_isolamento_appointments(self, client, auth_headers2, agendamento_appointment):
        data = agendamento_appointment.data_hora.strftime("%Y-%m-%d")
        res = client.get(f"/agendamento/appointments?data={data}", headers=auth_headers2)
        assert res.status_code == 404


class TestAlterarStatus:
    def test_confirmar_appointment(self, client, auth_headers, db, agendamento_config, agendamento_client, agendamento_servico):
        from backend.core.models import Appointment
        amanha = datetime.utcnow().replace(hour=14, minute=0) + timedelta(days=1)
        appt = Appointment(
            data_hora=amanha, status="pre_reservado",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            config_id=agendamento_config.id, client_id=agendamento_client.id,
            service_id=agendamento_servico.id,
        )
        db.add(appt); db.commit(); db.refresh(appt)

        res = client.put(f"/agendamento/appointments/{appt.id}/status?novo_status=confirmado", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["status"] == "confirmado"

    def test_cancelar_appointment(self, client, auth_headers, agendamento_appointment):
        res = client.put(f"/agendamento/appointments/{agendamento_appointment.id}/status?novo_status=cancelado", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["status"] == "cancelado"

    def test_concluir_appointment(self, client, auth_headers, agendamento_appointment):
        res = client.put(f"/agendamento/appointments/{agendamento_appointment.id}/status?novo_status=concluido", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["status"] == "concluido"

    def test_alterar_status_inexistente(self, client, auth_headers, agendamento_config):
        res = client.put("/agendamento/appointments/99999/status?novo_status=cancelado", headers=auth_headers)
        assert res.status_code == 404


class TestDeletarAppointment:
    def test_deletar_success(self, client, auth_headers, agendamento_appointment):
        res = client.delete(f"/agendamento/appointments/{agendamento_appointment.id}", headers=auth_headers)
        assert res.status_code == 200

    def test_deletar_inexistente(self, client, auth_headers, agendamento_config):
        res = client.delete("/agendamento/appointments/99999", headers=auth_headers)
        assert res.status_code == 404


class TestSlotsDisponiveis:
    def test_slots_com_horarios(self, client, auth_headers, agendamento_horarios, agendamento_servico):
        from datetime import date, timedelta
        hoje = date.today()
        dia_semana = hoje.weekday()
        if dia_semana >= 6:
            dia_util = hoje + timedelta(days=(7 - dia_semana))
        else:
            dia_util = hoje + timedelta(days=1) if dia_semana == 5 else hoje

        if dia_util.weekday() >= 6:
            dia_util = dia_util + timedelta(days=(7 - dia_util.weekday()))

        res = client.get(
            f"/agendamento/appointments/slots?data={dia_util.isoformat()}&service_id={agendamento_servico.id}",
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert "slots" in data
        assert isinstance(data["slots"], list)

    def test_slots_sem_horario_cadastrado(self, client, auth_headers, agendamento_config, agendamento_servico):
        res = client.get(
            f"/agendamento/appointments/slots?data=2026-01-05&service_id={agendamento_servico.id}",
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["slots"] == []
