"""Testes do módulo de agendamento: /agendamento/servicos."""
import pytest


SERVICO_BASE = {
    "nome": "Corte Feminino",
    "descricao": "Corte com lavagem",
    "duracao_minutos": 45,
    "preco": 60.0,
    "ativo": True,
}


class TestCriarServico:
    def test_criar_servico_success(self, client, auth_headers, agendamento_config):
        res = client.post("/agendamento/servicos", json=SERVICO_BASE, headers=auth_headers)
        assert res.status_code == 201
        data = res.json()
        assert data["nome"] == "Corte Feminino"
        assert data["duracao_minutos"] == 45
        assert data["preco"] == 60.0

    def test_criar_servico_sem_config(self, client, auth_headers):
        res = client.post("/agendamento/servicos", json=SERVICO_BASE, headers=auth_headers)
        assert res.status_code == 404

    def test_criar_servico_sem_auth(self, client):
        res = client.post("/agendamento/servicos", json=SERVICO_BASE)
        assert res.status_code == 401

    def test_criar_servico_campos_minimos(self, client, auth_headers, agendamento_config):
        payload = {"nome": "Barba", "duracao_minutos": 15}
        res = client.post("/agendamento/servicos", json=payload, headers=auth_headers)
        assert res.status_code == 201
        assert res.json()["preco"] is None


class TestListarServicos:
    def test_listar_servicos(self, client, auth_headers, agendamento_servico):
        res = client.get("/agendamento/servicos", headers=auth_headers)
        assert res.status_code == 200
        nomes = [s["nome"] for s in res.json()]
        assert "Corte Masculino" in nomes

    def test_listar_servicos_vazio(self, client, auth_headers, agendamento_config):
        res = client.get("/agendamento/servicos", headers=auth_headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_isolamento_servicos(self, client, auth_headers2, agendamento_servico):
        """Usuário 2 não vê serviços do usuário 1."""
        res = client.get("/agendamento/servicos", headers=auth_headers2)
        assert res.status_code == 404


class TestAtualizarServico:
    def test_atualizar_servico_success(self, client, auth_headers, agendamento_servico):
        payload = {**SERVICO_BASE, "nome": "Corte Premium", "preco": 80.0}
        res = client.put(f"/agendamento/servicos/{agendamento_servico.id}", json=payload, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["nome"] == "Corte Premium"
        assert res.json()["preco"] == 80.0

    def test_atualizar_servico_inexistente(self, client, auth_headers, agendamento_config):
        res = client.put("/agendamento/servicos/99999", json=SERVICO_BASE, headers=auth_headers)
        assert res.status_code == 404


class TestDeletarServico:
    def test_deletar_servico_success(self, client, auth_headers, agendamento_servico):
        res = client.delete(f"/agendamento/servicos/{agendamento_servico.id}", headers=auth_headers)
        assert res.status_code == 200
        res2 = client.get("/agendamento/servicos", headers=auth_headers)
        assert len(res2.json()) == 0

    def test_deletar_servico_inexistente(self, client, auth_headers, agendamento_config):
        res = client.delete("/agendamento/servicos/99999", headers=auth_headers)
        assert res.status_code == 404
