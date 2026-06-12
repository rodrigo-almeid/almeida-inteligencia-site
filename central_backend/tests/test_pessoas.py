"""Testes do router /pessoas — criação, listagem, principal, isolamento por usuário."""
import pytest


class TestCriarPessoa:
    def test_criar_pessoa_success(self, client, auth_headers):
        res = client.post("/pessoas/", json={"nome": "Empresa X", "principal": False}, headers=auth_headers)
        assert res.status_code == 201
        data = res.json()
        assert data["nome"] == "Empresa X"
        assert "id" in data

    def test_criar_pessoa_duplicada_mesmo_usuario(self, client, auth_headers, pessoa):
        # O mesmo nome para o mesmo usuário deve falhar
        res = client.post("/pessoas/", json={"nome": pessoa.nome, "principal": False}, headers=auth_headers)
        assert res.status_code == 400
        assert "já possui" in res.json()["detail"].lower()

    def test_criar_primeira_pessoa_vira_principal(self, client, auth_headers):
        res = client.post("/pessoas/", json={"nome": "Primeira", "principal": False}, headers=auth_headers)
        assert res.status_code == 201
        assert res.json()["principal"] is True

    def test_criar_sem_auth(self, client):
        res = client.post("/pessoas/", json={"nome": "Teste", "principal": False})
        assert res.status_code == 401

    def test_criar_sem_nome(self, client, auth_headers):
        res = client.post("/pessoas/", json={}, headers=auth_headers)
        assert res.status_code == 422


class TestListarPessoas:
    def test_listar_vazio(self, client, auth_headers):
        res = client.get("/pessoas/", headers=auth_headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_listar_com_dados(self, client, auth_headers, pessoa):
        res = client.get("/pessoas/", headers=auth_headers)
        assert res.status_code == 200
        nomes = [p["nome"] for p in res.json()]
        assert pessoa.nome in nomes

    def test_isolamento_entre_usuarios(self, client, auth_headers, auth_headers2, pessoa, pessoa2):
        """Usuário 1 não deve ver pessoas do usuário 2."""
        res = client.get("/pessoas/", headers=auth_headers)
        ids = [p["id"] for p in res.json()]
        assert pessoa2.id not in ids

    def test_listar_sem_auth(self, client):
        res = client.get("/pessoas/")
        assert res.status_code == 401


class TestDefinirPrincipal:
    def test_definir_principal(self, client, auth_headers, db, user):
        from backend.core.models import Pessoa
        p1 = Pessoa(nome="Pessoal", principal=True, user_id=user.id)
        p2 = Pessoa(nome="Trabalho", principal=False, user_id=user.id)
        db.add_all([p1, p2])
        db.commit()
        db.refresh(p1); db.refresh(p2)

        res = client.post(f"/pessoas/{p2.id}/principal", headers=auth_headers)
        assert res.status_code == 200
        db.expire_all()
        assert db.get(Pessoa, p2.id).principal is True
        assert db.get(Pessoa, p1.id).principal is False

    def test_definir_principal_pessoa_inexistente(self, client, auth_headers):
        res = client.post("/pessoas/99999/principal", headers=auth_headers)
        assert res.status_code == 404

    def test_definir_principal_de_outro_usuario(self, client, auth_headers, pessoa2):
        res = client.post(f"/pessoas/{pessoa2.id}/principal", headers=auth_headers)
        assert res.status_code == 404
