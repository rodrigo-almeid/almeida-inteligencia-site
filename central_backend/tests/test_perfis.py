"""Testes do endpoint /me/perfis."""
import pytest


class TestPerfis:
    def test_listar_perfis_usuario_sem_perfis(self, client, auth_headers):
        res = client.get("/me/perfis", headers=auth_headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_listar_perfis_com_perfil_atribuido(self, client, auth_headers, db, user):
        from backend.core.models import Perfil
        p = Perfil(nome="financeiro")
        db.add(p)
        db.commit()
        db.refresh(p)
        user.perfis.append(p)
        db.commit()

        res = client.get("/me/perfis", headers=auth_headers)
        assert res.status_code == 200
        assert "financeiro" in res.json()

    def test_listar_perfis_sem_auth(self, client):
        res = client.get("/me/perfis")
        assert res.status_code == 401

    def test_perfis_isolados_entre_usuarios(self, client, auth_headers, auth_headers2, db, user, user2):
        from backend.core.models import Perfil
        p = Perfil(nome="admin")
        db.add(p)
        db.commit()
        db.refresh(p)
        user.perfis.append(p)
        db.commit()

        res = client.get("/me/perfis", headers=auth_headers2)
        assert "admin" not in res.json()

    def test_multiplos_perfis(self, client, auth_headers, db, user):
        from backend.core.models import Perfil
        for nome in ["dashboard", "senhas", "abastecimento"]:
            p = Perfil(nome=nome)
            db.add(p)
            db.commit()
            db.refresh(p)
            user.perfis.append(p)
        db.commit()

        res = client.get("/me/perfis", headers=auth_headers)
        perfis = res.json()
        assert "dashboard" in perfis
        assert "senhas" in perfis
        assert "abastecimento" in perfis
