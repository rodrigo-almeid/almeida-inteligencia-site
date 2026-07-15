"""Testes do módulo financeiro: /contas/, /dividas/, /categorias/, /relatorios/."""
import pytest
from datetime import date


CONTA_BASE = {
    "descricao": "Luz",
    "vencimento": "2025-06-15",
    "valor": 200.0,
    "natureza": "despesa",
    "status": "pendente",
    "tipo_recorrencia": "unica",
}


class TestCriarConta:
    def test_criar_conta_success(self, client, auth_headers):
        res = client.post("/contas/", json=CONTA_BASE, headers=auth_headers)
        assert res.status_code == 201
        data = res.json()
        assert data["descricao"] == "Luz"
        assert data["valor"] == 200.0
        assert "id" in data

    def test_criar_conta_sem_auth(self, client):
        res = client.post("/contas/", json=CONTA_BASE)
        assert res.status_code == 401

    def test_criar_conta_campos_obrigatorios(self, client, auth_headers):
        res = client.post("/contas/", json={"descricao": "Incompleta"}, headers=auth_headers)
        assert res.status_code == 422

    def test_criar_conta_parcelada(self, client, auth_headers):
        payload = {
            **CONTA_BASE,
            "tipo_recorrencia": "parcelada",
            "total_parcelas": 3,
        }
        res = client.post("/contas/", json=payload, headers=auth_headers)
        assert res.status_code == 201
        # Deve retornar a primeira parcela
        assert res.json()["parcela_atual"] == 1

    def test_criar_receita(self, client, auth_headers):
        payload = {**CONTA_BASE, "natureza": "receita", "descricao": "Salário"}
        res = client.post("/contas/", json=payload, headers=auth_headers)
        assert res.status_code == 201
        assert res.json()["natureza"] == "receita"


class TestListarContas:
    def test_listar_contas_do_usuario(self, client, auth_headers, conta):
        res = client.get("/contas/", headers=auth_headers)
        assert res.status_code == 200
        ids = [c["id"] for c in res.json()]
        assert conta.id in ids

    def test_isolamento_entre_usuarios(self, client, auth_headers, auth_headers2, conta):
        """Usuário 2 não vê contas do usuário 1."""
        res = client.get("/contas/", headers=auth_headers2)
        ids = [c["id"] for c in res.json()]
        assert conta.id not in ids

    def test_filtro_por_mes(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        c_junho = Conta(descricao="Junho", vencimento=date(2025, 6, 1), valor=100.0, user_id=user.id, natureza="despesa", status="pendente", tipo_recorrencia="unica")
        c_julho = Conta(descricao="Julho", vencimento=date(2025, 7, 1), valor=200.0, user_id=user.id, natureza="despesa", status="pendente", tipo_recorrencia="unica")
        db.add_all([c_junho, c_julho])
        db.commit()

        res = client.get("/contas/?mes=6&ano=2025", headers=auth_headers)
        assert res.status_code == 200
        descricoes = [c["descricao"] for c in res.json()]
        assert "Junho" in descricoes
        assert "Julho" not in descricoes

    def test_filtro_por_ano(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        c2024 = Conta(descricao="2024", vencimento=date(2024, 1, 1), valor=50.0, user_id=user.id, natureza="despesa", status="pendente", tipo_recorrencia="unica")
        c2025 = Conta(descricao="2025", vencimento=date(2025, 1, 1), valor=75.0, user_id=user.id, natureza="despesa", status="pendente", tipo_recorrencia="unica")
        db.add_all([c2024, c2025])
        db.commit()

        res = client.get("/contas/?mes=1&ano=2025", headers=auth_headers)
        descricoes = [c["descricao"] for c in res.json()]
        assert "2025" in descricoes
        assert "2024" not in descricoes

    def test_listar_sem_auth(self, client):
        res = client.get("/contas/")
        assert res.status_code == 401


class TestAtualizarConta:
    def test_atualizar_conta_success(self, client, auth_headers, conta):
        payload = {**CONTA_BASE, "descricao": "Luz Atualizada", "status": "paga"}
        res = client.put(f"/contas/{conta.id}", json=payload, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["descricao"] == "Luz Atualizada"
        assert res.json()["status"] == "paga"

    def test_atualizar_conta_de_outro_usuario(self, client, auth_headers2, conta):
        res = client.put(f"/contas/{conta.id}", json=CONTA_BASE, headers=auth_headers2)
        assert res.status_code == 404

    def test_atualizar_conta_inexistente(self, client, auth_headers):
        res = client.put("/contas/99999", json=CONTA_BASE, headers=auth_headers)
        assert res.status_code == 404


class TestDeletarConta:
    def test_deletar_conta_success(self, client, auth_headers, conta, db):
        from backend.core.models import Conta
        res = client.delete(f"/contas/{conta.id}", headers=auth_headers)
        assert res.status_code == 204
        db.expire_all()
        assert db.get(Conta, conta.id) is None

    def test_deletar_conta_de_outro_usuario(self, client, auth_headers2, conta):
        res = client.delete(f"/contas/{conta.id}", headers=auth_headers2)
        assert res.status_code == 404

    def test_deletar_conta_inexistente(self, client, auth_headers):
        res = client.delete("/contas/99999", headers=auth_headers)
        assert res.status_code == 404


class TestCategorias:
    def test_criar_categoria(self, client, auth_headers):
        res = client.post("/categorias/", json={"nome": "Alimentação"}, headers=auth_headers)
        assert res.status_code == 201
        assert res.json()["nome"] == "Alimentação"

    def test_listar_categorias(self, client, auth_headers, db, user):
        from backend.core.models import Categoria
        db.add(Categoria(nome="Saúde", user_id=user.id))
        db.commit()
        res = client.get("/categorias/", headers=auth_headers)
        assert res.status_code == 200
        nomes = [c["nome"] for c in res.json()]
        assert "Saúde" in nomes

    def test_categoria_duplicada(self, client, auth_headers, db, user):
        from backend.core.models import Categoria
        db.add(Categoria(nome="Educação", user_id=user.id))
        db.commit()
        res = client.post("/categorias/", json={"nome": "Educação"}, headers=auth_headers)
        assert res.status_code in (400, 409)

    def test_deletar_categoria(self, client, auth_headers, db, user):
        from backend.core.models import Categoria
        c = Categoria(nome="Temp", user_id=user.id)
        db.add(c); db.commit(); db.refresh(c)
        res = client.delete(f"/categorias/{c.id}", headers=auth_headers)
        assert res.status_code == 200

    def test_deletar_categoria_nao_encontrada(self, client, auth_headers):
        res = client.delete("/categorias/99999", headers=auth_headers)
        assert res.status_code == 404

    def test_deletar_categoria_outro_usuario(self, client, auth_headers2, db, user):
        from backend.core.models import Categoria
        c = Categoria(nome="AlheiaTemp", user_id=user.id)
        db.add(c); db.commit(); db.refresh(c)
        res = client.delete(f"/categorias/{c.id}", headers=auth_headers2)
        assert res.status_code == 404


class TestDividas:
    DIVIDA_BASE = {
        "devedor": "João",
        "descricao": "Empréstimo",
        "vencimento": "2025-08-01",
        "valor": 500.0,
        "status": "pendente",
    }

    def test_criar_divida(self, client, auth_headers):
        res = client.post("/dividas/", json=self.DIVIDA_BASE, headers=auth_headers)
        assert res.status_code in (200, 201)
        assert res.json()["devedor"] == "João"

    def test_listar_dividas(self, client, auth_headers):
        client.post("/dividas/", json=self.DIVIDA_BASE, headers=auth_headers)
        res = client.get("/dividas/", headers=auth_headers)
        assert res.status_code == 200
        assert len(res.json()) >= 1

    def test_atualizar_divida_success(self, client, auth_headers, db, user):
        from backend.core.models import DividaTerceiro
        d = DividaTerceiro(devedor="Carlos", descricao="D", vencimento=date(2025, 9, 1), valor=300.0, status="pendente", user_id=user.id)
        db.add(d); db.commit(); db.refresh(d)
        payload = {**self.DIVIDA_BASE, "devedor": "Carlos Atualizado", "valor": 999.0}
        res = client.put(f"/dividas/{d.id}", json=payload, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["devedor"] == "Carlos Atualizado"
        assert res.json()["valor"] == 999.0

    def test_atualizar_divida_nao_encontrada(self, client, auth_headers):
        res = client.put("/dividas/99999", json=self.DIVIDA_BASE, headers=auth_headers)
        assert res.status_code == 404

    def test_atualizar_divida_outro_usuario(self, client, auth_headers2, db, user):
        from backend.core.models import DividaTerceiro
        d = DividaTerceiro(devedor="Pedro", descricao="D", vencimento=date(2025, 9, 1), valor=100.0, status="pendente", user_id=user.id)
        db.add(d); db.commit(); db.refresh(d)
        res = client.put(f"/dividas/{d.id}", json=self.DIVIDA_BASE, headers=auth_headers2)
        assert res.status_code == 404

    def test_deletar_divida(self, client, auth_headers, db, user):
        from backend.core.models import DividaTerceiro
        d = DividaTerceiro(devedor="Maria", descricao="Dívida", vencimento=date(2025, 9, 1), valor=100.0, status="pendente", user_id=user.id)
        db.add(d); db.commit(); db.refresh(d)
        res = client.delete(f"/dividas/{d.id}", headers=auth_headers)
        assert res.status_code in (200, 204)

    def test_deletar_divida_nao_encontrada(self, client, auth_headers):
        res = client.delete("/dividas/99999", headers=auth_headers)
        assert res.status_code == 404

    def test_deletar_divida_outro_usuario(self, client, auth_headers2, db, user):
        from backend.core.models import DividaTerceiro
        d = DividaTerceiro(devedor="Ana", descricao="D", vencimento=date(2025, 10, 1), valor=200.0, status="pendente", user_id=user.id)
        db.add(d); db.commit(); db.refresh(d)
        res = client.delete(f"/dividas/{d.id}", headers=auth_headers2)
        assert res.status_code == 404

    def test_isolamento_dividas(self, client, auth_headers2, db, user):
        from backend.core.models import DividaTerceiro
        d = DividaTerceiro(devedor="Ana", descricao="D", vencimento=date(2025, 10, 1), valor=200.0, status="pendente", user_id=user.id)
        db.add(d); db.commit(); db.refresh(d)
        res = client.get("/dividas/", headers=auth_headers2)
        ids = [x["id"] for x in res.json()]
        assert d.id not in ids


class TestContasParcelamento:
    def test_parcelada_gera_todas_parcelas(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        payload = {
            **CONTA_BASE,
            "tipo_recorrencia": "parcelada",
            "total_parcelas": 6,
            "vencimento": "2026-01-10",
        }
        res = client.post("/contas/", json=payload, headers=auth_headers)
        assert res.status_code == 201
        db.expire_all()
        total = db.query(Conta).filter(Conta.user_id == user.id).count()
        assert total == 6

    def test_parcelada_vencimentos_mensais(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        payload = {
            **CONTA_BASE,
            "tipo_recorrencia": "parcelada",
            "total_parcelas": 3,
            "vencimento": "2026-01-10",
        }
        client.post("/contas/", json=payload, headers=auth_headers)
        db.expire_all()
        contas = db.query(Conta).filter(Conta.user_id == user.id).order_by(Conta.vencimento).all()
        meses = [c.vencimento.month for c in contas]
        assert meses == [1, 2, 3]

    def test_parcelada_retorna_primeira_parcela(self, client, auth_headers):
        payload = {
            **CONTA_BASE,
            "tipo_recorrencia": "parcelada",
            "total_parcelas": 4,
        }
        res = client.post("/contas/", json=payload, headers=auth_headers)
        assert res.json()["parcela_atual"] == 1

    def test_parcelada_1x_cria_conta_simples(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        payload = {**CONTA_BASE, "tipo_recorrencia": "parcelada", "total_parcelas": 1}
        client.post("/contas/", json=payload, headers=auth_headers)
        db.expire_all()
        total = db.query(Conta).filter(Conta.user_id == user.id).count()
        assert total == 1

    def test_filtro_competencia(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        c = Conta(
            descricao="Com Competência", vencimento=date(2026, 5, 30), competencia="2026-06",
            valor=200.0, natureza="despesa", status="pendente", tipo_recorrencia="unica", user_id=user.id
        )
        db.add(c); db.commit()
        res = client.get("/contas/?mes=6&ano=2026", headers=auth_headers)
        descricoes = [c["descricao"] for c in res.json()]
        assert "Com Competência" in descricoes

    def test_filtro_exclui_competencia_errada(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        c = Conta(
            descricao="Competência Julho", vencimento=date(2026, 6, 1), competencia="2026-07",
            valor=100.0, natureza="despesa", status="pendente", tipo_recorrencia="unica", user_id=user.id
        )
        db.add(c); db.commit()
        res = client.get("/contas/?mes=6&ano=2026", headers=auth_headers)
        descricoes = [c["descricao"] for c in res.json()]
        assert "Competência Julho" not in descricoes

    def test_parcelada_com_competencia_propaga_meses(self, client, auth_headers, db, user):
        """Cobre contas.py:41-42 — competencia é ajustada mês a mês em cada parcela."""
        from backend.core.models import Conta
        payload = {
            **CONTA_BASE,
            "tipo_recorrencia": "parcelada",
            "total_parcelas": 3,
            "vencimento": "2026-01-10",
            "competencia": "2026-01",
        }
        res = client.post("/contas/", json=payload, headers=auth_headers)
        assert res.status_code == 201
        db.expire_all()
        parcelas = db.query(Conta).filter(Conta.user_id == user.id).order_by(Conta.parcela_atual).all()
        competencias = [p.competencia for p in parcelas]
        assert competencias == ["2026-01", "2026-02", "2026-03"]


class TestMigrarContas:
    def test_migrar_duplica_para_proximo_mes(self, client, auth_headers, conta, db):
        """conta fixture: vencimento=2025-06-10, sem competencia — deve duplicar para 2025-07-10,
        mesmo valor, status resetado para pendente, original intacta."""
        from backend.core.models import Conta
        res = client.post("/contas/migrar", json={"conta_ids": [conta.id]}, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["migradas"] == 1
        nova = data["novas_contas"][0]
        assert nova["id"] != conta.id
        assert nova["vencimento"] == "2025-07-10"
        assert nova["valor"] == conta.valor
        assert nova["status"] == "pendente"
        assert nova["descricao"] == conta.descricao

        db.expire_all()
        original = db.get(Conta, conta.id)
        assert original is not None
        assert original.vencimento == date(2025, 6, 10)

    def test_migrar_avanca_competencia(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        c = Conta(descricao="Internet", vencimento=date(2026, 1, 31), competencia="2026-01",
                   valor=99.9, natureza="despesa", status="paga", tipo_recorrencia="unica", user_id=user.id)
        db.add(c); db.commit(); db.refresh(c)
        res = client.post("/contas/migrar", json={"conta_ids": [c.id]}, headers=auth_headers)
        assert res.status_code == 200
        nova = res.json()["novas_contas"][0]
        # Janeiro tem 31 dias, fevereiro só 28/29 — deve ajustar o dia (rollover)
        assert nova["vencimento"] == "2026-02-28"
        assert nova["competencia"] == "2026-02"

    def test_migrar_reseta_status_pago(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        c = Conta(descricao="Cartão", vencimento=date(2026, 3, 5), valor=300.0,
                   natureza="despesa", status="paga", tipo_recorrencia="unica", user_id=user.id)
        db.add(c); db.commit(); db.refresh(c)
        res = client.post("/contas/migrar", json={"conta_ids": [c.id]}, headers=auth_headers)
        nova = res.json()["novas_contas"][0]
        assert nova["status"] == "pendente"

    def test_migrar_multiplas_contas(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        c1 = Conta(descricao="A", vencimento=date(2026, 4, 1), valor=10.0, natureza="despesa", status="pendente", tipo_recorrencia="unica", user_id=user.id)
        c2 = Conta(descricao="B", vencimento=date(2026, 4, 2), valor=20.0, natureza="despesa", status="pendente", tipo_recorrencia="unica", user_id=user.id)
        db.add_all([c1, c2]); db.commit(); db.refresh(c1); db.refresh(c2)
        res = client.post("/contas/migrar", json={"conta_ids": [c1.id, c2.id]}, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["migradas"] == 2

    def test_migrar_ignora_conta_de_outro_usuario(self, client, auth_headers2, conta):
        res = client.post("/contas/migrar", json={"conta_ids": [conta.id]}, headers=auth_headers2)
        assert res.status_code == 404

    def test_migrar_ids_inexistentes(self, client, auth_headers):
        res = client.post("/contas/migrar", json={"conta_ids": [99999]}, headers=auth_headers)
        assert res.status_code == 404

    def test_migrar_sem_auth(self, client, conta):
        res = client.post("/contas/migrar", json={"conta_ids": [conta.id]})
        assert res.status_code == 401


class TestRelatorios:
    def test_exportar_excel(self, client, auth_headers, conta):
        res = client.get("/relatorios/excel/contas", headers=auth_headers)
        assert res.status_code == 200
        assert "spreadsheet" in res.headers["content-type"]

    def test_exportar_excel_com_filtro_mes(self, client, auth_headers, conta):
        res = client.get("/relatorios/excel/contas?mes=6&ano=2025", headers=auth_headers)
        assert res.status_code == 200
        assert "spreadsheet" in res.headers["content-type"]
        assert "contas_2025_06.xlsx" in res.headers["content-disposition"]

    def test_exportar_excel_sem_contas(self, client, auth_headers):
        res = client.get("/relatorios/excel/contas?mes=1&ano=2000", headers=auth_headers)
        assert res.status_code == 200

    def test_exportar_excel_saldo_negativo(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        db.add(Conta(descricao="Receita", vencimento=date(2025, 3, 1), valor=100.0,
                     natureza="receita", status="paga", tipo_recorrencia="unica", user_id=user.id))
        db.add(Conta(descricao="Despesa", vencimento=date(2025, 3, 1), valor=500.0,
                     natureza="despesa", status="paga", tipo_recorrencia="unica", user_id=user.id))
        db.commit()
        res = client.get("/relatorios/excel/contas?mes=3&ano=2025", headers=auth_headers)
        assert res.status_code == 200

    def test_exportar_pdf(self, client, auth_headers, conta):
        res = client.get("/relatorios/pdf/contas", headers=auth_headers)
        assert res.status_code == 200
        assert "pdf" in res.headers["content-type"]

    def test_exportar_pdf_com_filtro_mes(self, client, auth_headers, conta):
        res = client.get("/relatorios/pdf/contas?mes=6&ano=2025", headers=auth_headers)
        assert res.status_code == 200
        assert "pdf" in res.headers["content-type"]
        assert "contas_2025_06.pdf" in res.headers["content-disposition"]

    def test_exportar_pdf_saldo_negativo(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        db.add(Conta(descricao="Receita", vencimento=date(2025, 4, 1), valor=50.0,
                     natureza="receita", status="paga", tipo_recorrencia="unica", user_id=user.id))
        db.add(Conta(descricao="Despesa", vencimento=date(2025, 4, 1), valor=800.0,
                     natureza="despesa", status="paga", tipo_recorrencia="unica", user_id=user.id))
        db.commit()
        res = client.get("/relatorios/pdf/contas?mes=4&ano=2025", headers=auth_headers)
        assert res.status_code == 200

    def test_exportar_pdf_com_categoria(self, client, auth_headers, db, user):
        from backend.core.models import Conta, Categoria
        cat = Categoria(nome="Casa", user_id=user.id)
        db.add(cat); db.commit(); db.refresh(cat)
        db.add(Conta(descricao="Aluguel <teste> & co", vencimento=date(2025, 5, 1), valor=1000.0,
                     natureza="despesa", status="paga", tipo_recorrencia="unica",
                     categoria_id=cat.id, user_id=user.id))
        db.commit()
        res = client.get("/relatorios/pdf/contas?mes=5&ano=2025", headers=auth_headers)
        assert res.status_code == 200

    def test_exportar_sem_auth(self, client):
        assert client.get("/relatorios/excel/contas").status_code == 401
        assert client.get("/relatorios/pdf/contas").status_code == 401
