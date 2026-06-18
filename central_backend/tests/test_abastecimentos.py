"""Testes do módulo Combustível: /abastecimentos/."""
import pytest


ABAST_BASE = {
    "data": "2026-06-01",
    "tipo_combustivel": "gasolina",
    "km_atual": 50000.0,
    "litros": 40.0,
    "valor_unitario": 6.50,
    "valor_total": 260.0,
    "forma_pagamento": "debito",
    "tanque_cheio": True,
}


class TestCriarAbastecimento:
    def test_criar_success(self, client, auth_headers):
        res = client.post("/abastecimentos/", json=ABAST_BASE, headers=auth_headers)
        assert res.status_code == 201
        data = res.json()
        assert data["tipo_combustivel"] == "gasolina"
        assert data["valor_total"] == 260.0
        assert "id" in data

    def test_criar_sem_auth(self, client):
        res = client.post("/abastecimentos/", json=ABAST_BASE)
        assert res.status_code == 401

    def test_criar_campos_obrigatorios(self, client, auth_headers):
        res = client.post("/abastecimentos/", json={"tipo_combustivel": "gasolina"}, headers=auth_headers)
        assert res.status_code == 422

    def test_primeiro_abastecimento_sem_km_anterior(self, client, auth_headers):
        res = client.post("/abastecimentos/", json=ABAST_BASE, headers=auth_headers)
        assert res.status_code == 201
        assert res.json()["km_anterior"] is None

    def test_segundo_abastecimento_calcula_km_anterior(self, client, auth_headers):
        client.post("/abastecimentos/", json=ABAST_BASE, headers=auth_headers)
        segundo = {**ABAST_BASE, "km_atual": 50500.0, "data": "2026-06-15"}
        res = client.post("/abastecimentos/", json=segundo, headers=auth_headers)
        assert res.status_code == 201
        data = res.json()
        assert data["km_anterior"] == 50000.0
        assert data["distancia_percorrida"] == pytest.approx(500.0)

    def test_media_consumo_calculada(self, client, auth_headers):
        client.post("/abastecimentos/", json=ABAST_BASE, headers=auth_headers)
        segundo = {**ABAST_BASE, "km_atual": 50400.0, "litros": 40.0, "data": "2026-06-15"}
        res = client.post("/abastecimentos/", json=segundo, headers=auth_headers)
        assert res.status_code == 201
        assert res.json()["media_consumo"] == pytest.approx(10.0)

    def test_tanque_nao_cheio_nao_calcula_media(self, client, auth_headers):
        client.post("/abastecimentos/", json=ABAST_BASE, headers=auth_headers)
        segundo = {**ABAST_BASE, "km_atual": 50400.0, "tanque_cheio": False, "data": "2026-06-15"}
        res = client.post("/abastecimentos/", json=segundo, headers=auth_headers)
        assert res.status_code == 201
        assert res.json()["media_consumo"] is None

    def test_etanol(self, client, auth_headers):
        payload = {**ABAST_BASE, "tipo_combustivel": "etanol", "valor_unitario": 4.20, "valor_total": 168.0}
        res = client.post("/abastecimentos/", json=payload, headers=auth_headers)
        assert res.status_code == 201
        assert res.json()["tipo_combustivel"] == "etanol"


class TestListarAbastecimentos:
    def test_listar_sem_filtro(self, client, auth_headers):
        client.post("/abastecimentos/", json=ABAST_BASE, headers=auth_headers)
        res = client.get("/abastecimentos/", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert "abastecimentos" in data
        assert "estatisticas" in data
        assert len(data["abastecimentos"]) >= 1

    def test_listar_com_filtro_mes(self, client, auth_headers):
        client.post("/abastecimentos/", json=ABAST_BASE, headers=auth_headers)
        res = client.get("/abastecimentos/?mes=6&ano=2026", headers=auth_headers)
        assert res.status_code == 200
        abast = res.json()["abastecimentos"]
        assert len(abast) >= 1
        assert all(a["data"].startswith("2026-06") for a in abast)

    def test_filtro_mes_diferente_retorna_vazio(self, client, auth_headers):
        client.post("/abastecimentos/", json=ABAST_BASE, headers=auth_headers)
        res = client.get("/abastecimentos/?mes=1&ano=2025", headers=auth_headers)
        assert res.json()["abastecimentos"] == []

    def test_isolamento_entre_usuarios(self, client, auth_headers, auth_headers2):
        client.post("/abastecimentos/", json=ABAST_BASE, headers=auth_headers)
        res = client.get("/abastecimentos/", headers=auth_headers2)
        assert res.json()["abastecimentos"] == []

    def test_listar_sem_auth(self, client):
        res = client.get("/abastecimentos/")
        assert res.status_code == 401

    def test_estatisticas_mediana_gasolina(self, client, auth_headers):
        client.post("/abastecimentos/", json=ABAST_BASE, headers=auth_headers)
        segundo = {**ABAST_BASE, "km_atual": 50400.0, "data": "2026-06-15"}
        client.post("/abastecimentos/", json=segundo, headers=auth_headers)
        res = client.get("/abastecimentos/", headers=auth_headers)
        estat = res.json()["estatisticas"]
        assert "mediana_gasolina" in estat
        assert "mediana_etanol" in estat

    def test_estatisticas_sem_abastecimentos_retorna_zero(self, client, auth_headers):
        res = client.get("/abastecimentos/", headers=auth_headers)
        estat = res.json()["estatisticas"]
        assert estat["mediana_gasolina"] == 0.0
        assert estat["mediana_etanol"] == 0.0


class TestExcluirAbastecimento:
    def test_excluir_success(self, client, auth_headers):
        res = client.post("/abastecimentos/", json=ABAST_BASE, headers=auth_headers)
        abast_id = res.json()["id"]
        del_res = client.delete(f"/abastecimentos/{abast_id}", headers=auth_headers)
        assert del_res.status_code == 204

        lista = client.get("/abastecimentos/", headers=auth_headers)
        ids = [a["id"] for a in lista.json()["abastecimentos"]]
        assert abast_id not in ids

    def test_excluir_de_outro_usuario(self, client, auth_headers, auth_headers2):
        res = client.post("/abastecimentos/", json=ABAST_BASE, headers=auth_headers)
        abast_id = res.json()["id"]
        del_res = client.delete(f"/abastecimentos/{abast_id}", headers=auth_headers2)
        assert del_res.status_code == 404

    def test_excluir_inexistente(self, client, auth_headers):
        res = client.delete("/abastecimentos/99999", headers=auth_headers)
        assert res.status_code == 404

    def test_excluir_sem_auth(self, client):
        res = client.delete("/abastecimentos/1")
        assert res.status_code == 401


class TestRecalcularMedias:
    def test_recalcular_success(self, client, auth_headers):
        client.post("/abastecimentos/", json=ABAST_BASE, headers=auth_headers)
        res = client.post("/abastecimentos/recalcular", headers=auth_headers)
        assert res.status_code == 200
        assert "recalculados" in res.json()["mensagem"]

    def test_recalcular_sem_auth(self, client):
        res = client.post("/abastecimentos/recalcular")
        assert res.status_code == 401

    def test_recalcular_corrige_media(self, client, auth_headers):
        client.post("/abastecimentos/", json=ABAST_BASE, headers=auth_headers)
        segundo = {**ABAST_BASE, "km_atual": 50400.0, "litros": 40.0, "data": "2026-06-15"}
        client.post("/abastecimentos/", json=segundo, headers=auth_headers)
        res = client.post("/abastecimentos/recalcular", headers=auth_headers)
        assert res.status_code == 200
        lista = client.get("/abastecimentos/", headers=auth_headers)
        abasts = lista.json()["abastecimentos"]
        com_media = [a for a in abasts if a["media_consumo"] is not None]
        assert len(com_media) >= 1
