"""Testes do módulo de agendamento: /agendamento/clients."""
import pytest


class TestListarClients:
    def test_listar_clients(self, client, auth_headers, agendamento_client):
        res = client.get("/agendamento/clients", headers=auth_headers)
        assert res.status_code == 200
        telefones = [c["telefone"] for c in res.json()]
        assert "5543999999999" in telefones

    def test_listar_clients_vazio(self, client, auth_headers, agendamento_config):
        res = client.get("/agendamento/clients", headers=auth_headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_listar_sem_config(self, client, auth_headers):
        res = client.get("/agendamento/clients", headers=auth_headers)
        assert res.status_code == 404

    def test_listar_sem_auth(self, client):
        res = client.get("/agendamento/clients")
        assert res.status_code == 401

    def test_isolamento_clients(self, client, auth_headers2, agendamento_client):
        res = client.get("/agendamento/clients", headers=auth_headers2)
        assert res.status_code == 404


class TestDetalheClient:
    def test_detalhe_success(self, client, auth_headers, agendamento_client):
        res = client.get(f"/agendamento/clients/{agendamento_client.id}", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["telefone"] == "5543999999999"
        assert data["nome"] == "João Teste"
        assert "agendamentos" in data

    def test_detalhe_com_agendamento(self, client, auth_headers, agendamento_appointment):
        cid = agendamento_appointment.client_id
        res = client.get(f"/agendamento/clients/{cid}", headers=auth_headers)
        assert res.status_code == 200
        assert len(res.json()["agendamentos"]) >= 1

    def test_detalhe_inexistente(self, client, auth_headers, agendamento_config):
        res = client.get("/agendamento/clients/99999", headers=auth_headers)
        assert res.status_code == 404

    def test_detalhe_outro_usuario(self, client, auth_headers2, agendamento_client):
        res = client.get(f"/agendamento/clients/{agendamento_client.id}", headers=auth_headers2)
        assert res.status_code == 404
