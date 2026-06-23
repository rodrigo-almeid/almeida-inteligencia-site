"""Testes do módulo de agendamento: /agendamento/horarios."""
import pytest


HORARIOS_BATCH = [
    {"dia_semana": 0, "hora_inicio": "09:00", "hora_fim": "18:00", "ativo": True},
    {"dia_semana": 1, "hora_inicio": "09:00", "hora_fim": "18:00", "ativo": True},
    {"dia_semana": 2, "hora_inicio": "10:00", "hora_fim": "17:00", "ativo": True},
    {"dia_semana": 5, "hora_inicio": "09:00", "hora_fim": "13:00", "ativo": True},
    {"dia_semana": 6, "hora_inicio": "00:00", "hora_fim": "00:00", "ativo": False},
]


class TestSalvarHorarios:
    def test_salvar_horarios_batch(self, client, auth_headers, agendamento_config):
        res = client.post("/agendamento/horarios", json=HORARIOS_BATCH, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 5
        assert data[0]["dia_semana"] == 0
        assert data[0]["hora_inicio"] == "09:00"

    def test_salvar_horarios_substitui_anteriores(self, client, auth_headers, agendamento_config):
        client.post("/agendamento/horarios", json=HORARIOS_BATCH, headers=auth_headers)
        novos = [{"dia_semana": 0, "hora_inicio": "08:00", "hora_fim": "20:00", "ativo": True}]
        res = client.post("/agendamento/horarios", json=novos, headers=auth_headers)
        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["hora_inicio"] == "08:00"

    def test_salvar_horarios_sem_config(self, client, auth_headers):
        res = client.post("/agendamento/horarios", json=HORARIOS_BATCH, headers=auth_headers)
        assert res.status_code == 404

    def test_salvar_horarios_sem_auth(self, client):
        res = client.post("/agendamento/horarios", json=HORARIOS_BATCH)
        assert res.status_code == 401


class TestListarHorarios:
    def test_listar_horarios(self, client, auth_headers, agendamento_horarios):
        res = client.get("/agendamento/horarios", headers=auth_headers)
        assert res.status_code == 200
        assert len(res.json()) == 6

    def test_listar_horarios_ordenados_por_dia(self, client, auth_headers, agendamento_horarios):
        res = client.get("/agendamento/horarios", headers=auth_headers)
        dias = [h["dia_semana"] for h in res.json()]
        assert dias == sorted(dias)

    def test_listar_horarios_vazio(self, client, auth_headers, agendamento_config):
        res = client.get("/agendamento/horarios", headers=auth_headers)
        assert res.status_code == 200
        assert res.json() == []


class TestDeletarHorario:
    def test_deletar_horario_success(self, client, auth_headers, agendamento_horarios):
        h_id = agendamento_horarios[0].id
        res = client.delete(f"/agendamento/horarios/{h_id}", headers=auth_headers)
        assert res.status_code == 200
        res2 = client.get("/agendamento/horarios", headers=auth_headers)
        assert len(res2.json()) == 5

    def test_deletar_horario_inexistente(self, client, auth_headers, agendamento_config):
        res = client.delete("/agendamento/horarios/99999", headers=auth_headers)
        assert res.status_code == 404
