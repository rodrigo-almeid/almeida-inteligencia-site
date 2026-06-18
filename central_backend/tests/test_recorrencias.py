"""Testes do motor de recorrências: /recorrencias/processar/."""
import pytest
from datetime import date


def _criar_conta(db, user, tipo_recorrencia="vitalícia", mes=6, ano=2026,
                 parcela_atual=1, total_parcelas=None, processado=0):
    from backend.core.models import Conta
    c = Conta(
        descricao="Conta Recorrente",
        vencimento=date(ano, mes, 10),
        valor=100.0,
        natureza="despesa",
        status="pendente",
        tipo_recorrencia=tipo_recorrencia,
        parcela_atual=parcela_atual,
        total_parcelas=total_parcelas,
        mes_seguinte_processado=processado,
        user_id=user.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


class TestProcessarRecorrencias:
    def test_gera_conta_vitalicia(self, client, auth_headers, db, user):
        _criar_conta(db, user, tipo_recorrencia="vitalícia", mes=6, ano=2026)
        res = client.post("/recorrencias/processar/?mes=6&ano=2026", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["mensagem"].startswith("1")

    def test_gera_conta_parcelada_com_parcelas_restantes(self, client, auth_headers, db, user):
        _criar_conta(db, user, tipo_recorrencia="parcelada", mes=6, ano=2026,
                     parcela_atual=1, total_parcelas=3)
        res = client.post("/recorrencias/processar/?mes=6&ano=2026", headers=auth_headers)
        assert res.status_code == 200
        assert "1" in res.json()["mensagem"]

    def test_nao_gera_quando_parcela_esgotada(self, client, auth_headers, db, user):
        _criar_conta(db, user, tipo_recorrencia="parcelada", mes=6, ano=2026,
                     parcela_atual=3, total_parcelas=3)
        res = client.post("/recorrencias/processar/?mes=6&ano=2026", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["mensagem"].startswith("0")

    def test_nao_processa_conta_ja_processada(self, client, auth_headers, db, user):
        _criar_conta(db, user, tipo_recorrencia="vitalícia", mes=6, ano=2026, processado=1)
        res = client.post("/recorrencias/processar/?mes=6&ano=2026", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["mensagem"].startswith("0")

    def test_nao_processa_conta_unica(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        c = Conta(
            descricao="Única", vencimento=date(2026, 6, 1), valor=50.0,
            natureza="despesa", status="pendente", tipo_recorrencia="unica",
            mes_seguinte_processado=0, user_id=user.id
        )
        db.add(c); db.commit()
        res = client.post("/recorrencias/processar/?mes=6&ano=2026", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["mensagem"].startswith("0")

    def test_conta_gerada_tem_vencimento_mes_seguinte(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        _criar_conta(db, user, tipo_recorrencia="vitalícia", mes=6, ano=2026)
        client.post("/recorrencias/processar/?mes=6&ano=2026", headers=auth_headers)
        contas = db.query(Conta).filter(Conta.user_id == user.id).all()
        db.expire_all()
        contas = db.query(Conta).filter(Conta.user_id == user.id).all()
        vencimentos = [c.vencimento.month for c in contas]
        assert 7 in vencimentos

    def test_marca_original_como_processada(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        original = _criar_conta(db, user, tipo_recorrencia="vitalícia", mes=6, ano=2026)
        client.post("/recorrencias/processar/?mes=6&ano=2026", headers=auth_headers)
        db.expire_all()
        assert db.get(Conta, original.id).mes_seguinte_processado == 1

    def test_isolamento_entre_usuarios(self, client, auth_headers, auth_headers2, db, user, user2):
        _criar_conta(db, user, tipo_recorrencia="vitalícia", mes=6, ano=2026)
        res = client.post("/recorrencias/processar/?mes=6&ano=2026", headers=auth_headers2)
        assert res.status_code == 200
        assert res.json()["mensagem"].startswith("0")

    def test_processar_sem_auth(self, client):
        res = client.post("/recorrencias/processar/?mes=6&ano=2026")
        assert res.status_code == 401

    def test_mes_dezembro_gera_janeiro_ano_seguinte(self, client, auth_headers, db, user):
        from backend.core.models import Conta
        _criar_conta(db, user, tipo_recorrencia="vitalícia", mes=12, ano=2025)
        client.post("/recorrencias/processar/?mes=12&ano=2025", headers=auth_headers)
        db.expire_all()
        contas = db.query(Conta).filter(Conta.user_id == user.id).all()
        geradas = [c for c in contas if c.vencimento.month == 1 and c.vencimento.year == 2026]
        assert len(geradas) == 1
