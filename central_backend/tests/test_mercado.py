"""Testes do módulo Mercado: /mercado/compras."""
import pytest


COMPRA_BASE = {
    "data": "2026-06-01",
    "loja": "Assaí",
    "forma_pagamento": "debito",
    "bandeira_vale": None,
    "itens": [
        {"nome": "Arroz", "valor": 25.90, "categoria": "Grãos e Cereais"},
        {"nome": "Feijão", "valor": 12.50, "categoria": "Grãos e Cereais"},
    ],
}


class TestCriarCompra:
    def test_criar_compra_success(self, client, auth_headers):
        res = client.post("/mercado/compras", json=COMPRA_BASE, headers=auth_headers)
        assert res.status_code == 201
        data = res.json()
        assert data["loja"] == "Assaí"
        assert data["forma_pagamento"] == "debito"
        assert data["valor_total"] == pytest.approx(38.40)
        assert len(data["itens"]) == 2

    def test_criar_compra_sem_auth(self, client):
        res = client.post("/mercado/compras", json=COMPRA_BASE)
        assert res.status_code == 401

    def test_criar_compra_sem_itens(self, client, auth_headers):
        payload = {**COMPRA_BASE, "itens": []}
        res = client.post("/mercado/compras", json=payload, headers=auth_headers)
        assert res.status_code == 400

    def test_criar_compra_vale_com_bandeira(self, client, auth_headers):
        payload = {
            **COMPRA_BASE,
            "forma_pagamento": "vale_alimentacao",
            "bandeira_vale": "alelo",
        }
        res = client.post("/mercado/compras", json=payload, headers=auth_headers)
        assert res.status_code == 201
        assert res.json()["bandeira_vale"] == "alelo"

    def test_criar_compra_debito_ignora_bandeira(self, client, auth_headers):
        payload = {**COMPRA_BASE, "forma_pagamento": "debito", "bandeira_vale": "ticket"}
        res = client.post("/mercado/compras", json=payload, headers=auth_headers)
        assert res.status_code == 201
        assert res.json()["bandeira_vale"] is None

    def test_valor_total_calculado_automaticamente(self, client, auth_headers):
        payload = {
            **COMPRA_BASE,
            "itens": [
                {"nome": "Leite", "valor": 5.00},
                {"nome": "Pão", "valor": 8.00},
                {"nome": "Manteiga", "valor": 12.00},
            ],
        }
        res = client.post("/mercado/compras", json=payload, headers=auth_headers)
        assert res.status_code == 201
        assert res.json()["valor_total"] == pytest.approx(25.00)

    def test_loja_opcional(self, client, auth_headers):
        payload = {**COMPRA_BASE, "loja": None}
        res = client.post("/mercado/compras", json=payload, headers=auth_headers)
        assert res.status_code == 201
        assert res.json()["loja"] is None

    def test_categoria_item_opcional(self, client, auth_headers):
        payload = {**COMPRA_BASE, "itens": [{"nome": "Biscoito", "valor": 3.50}]}
        res = client.post("/mercado/compras", json=payload, headers=auth_headers)
        assert res.status_code == 201
        assert res.json()["itens"][0]["categoria"] is None


class TestListarCompras:
    def test_listar_compras_do_mes(self, client, auth_headers):
        client.post("/mercado/compras", json=COMPRA_BASE, headers=auth_headers)
        res = client.get("/mercado/compras?mes=6&ano=2026", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["compras"]) >= 1
        assert "resumo" in data

    def test_resumo_totais(self, client, auth_headers):
        client.post("/mercado/compras", json=COMPRA_BASE, headers=auth_headers)
        res = client.get("/mercado/compras?mes=6&ano=2026", headers=auth_headers)
        resumo = res.json()["resumo"]
        assert resumo["total_mes"] >= 38.40
        assert resumo["total_debito"] >= 38.40
        assert resumo["total_credito"] == 0.0
        assert resumo["total_vale"] == 0.0

    def test_filtro_mes_nao_retorna_outros_meses(self, client, auth_headers):
        client.post("/mercado/compras", json=COMPRA_BASE, headers=auth_headers)
        res = client.get("/mercado/compras?mes=5&ano=2026", headers=auth_headers)
        assert res.json()["resumo"]["qtd_compras"] == 0

    def test_isolamento_entre_usuarios(self, client, auth_headers, auth_headers2):
        client.post("/mercado/compras", json=COMPRA_BASE, headers=auth_headers)
        res = client.get("/mercado/compras?mes=6&ano=2026", headers=auth_headers2)
        assert res.json()["resumo"]["qtd_compras"] == 0

    def test_listar_sem_auth(self, client):
        res = client.get("/mercado/compras")
        assert res.status_code == 401


class TestResumoMensal:
    def test_resumo_separa_debito_e_vale(self, client, auth_headers):
        client.post("/mercado/compras", json=COMPRA_BASE, headers=auth_headers)
        vale = {
            **COMPRA_BASE,
            "forma_pagamento": "vale_alimentacao",
            "bandeira_vale": "ticket",
            "itens": [{"nome": "Frango", "valor": 30.0}],
        }
        client.post("/mercado/compras", json=vale, headers=auth_headers)
        res = client.get("/mercado/compras?mes=6&ano=2026", headers=auth_headers)
        resumo = res.json()["resumo"]
        assert resumo["total_debito"] == pytest.approx(38.40)
        assert resumo["total_vale"] == pytest.approx(30.0)
        assert resumo["total_credito"] == 0.0

    def test_resumo_qtd_compras(self, client, auth_headers):
        for _ in range(3):
            client.post("/mercado/compras", json=COMPRA_BASE, headers=auth_headers)
        res = client.get("/mercado/compras?mes=6&ano=2026", headers=auth_headers)
        assert res.json()["resumo"]["qtd_compras"] == 3

    def test_resumo_mes_sem_compras(self, client, auth_headers):
        res = client.get("/mercado/compras?mes=1&ano=2020", headers=auth_headers)
        resumo = res.json()["resumo"]
        assert resumo["total_mes"] == 0.0
        assert resumo["qtd_compras"] == 0

    def test_compras_ordenadas_por_data_desc(self, client, auth_headers):
        payload_antiga = {**COMPRA_BASE, "data": "2026-06-01"}
        payload_nova = {**COMPRA_BASE, "data": "2026-06-20"}
        client.post("/mercado/compras", json=payload_antiga, headers=auth_headers)
        client.post("/mercado/compras", json=payload_nova, headers=auth_headers)
        res = client.get("/mercado/compras?mes=6&ano=2026", headers=auth_headers)
        compras = res.json()["compras"]
        assert compras[0]["data"] >= compras[1]["data"]


class TestExcluirCompra:
    def test_excluir_compra_success(self, client, auth_headers):
        res = client.post("/mercado/compras", json=COMPRA_BASE, headers=auth_headers)
        compra_id = res.json()["id"]
        del_res = client.delete(f"/mercado/compras/{compra_id}", headers=auth_headers)
        assert del_res.status_code == 204

        lista = client.get("/mercado/compras?mes=6&ano=2026", headers=auth_headers)
        ids = [c["id"] for c in lista.json()["compras"]]
        assert compra_id not in ids

    def test_excluir_compra_de_outro_usuario(self, client, auth_headers, auth_headers2):
        res = client.post("/mercado/compras", json=COMPRA_BASE, headers=auth_headers)
        compra_id = res.json()["id"]
        del_res = client.delete(f"/mercado/compras/{compra_id}", headers=auth_headers2)
        assert del_res.status_code == 404

    def test_excluir_compra_inexistente(self, client, auth_headers):
        res = client.delete("/mercado/compras/99999", headers=auth_headers)
        assert res.status_code == 404

    def test_excluir_sem_auth(self, client):
        res = client.delete("/mercado/compras/1")
        assert res.status_code == 401
