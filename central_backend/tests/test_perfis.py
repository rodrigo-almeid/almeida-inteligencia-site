"""Testes do endpoint /me/perfis."""
import pytest
from backend.core.models import User, Perfil
from backend.core.security import get_password_hash


NOPERFIL_EMAIL = "noperfil@teste.com"
NOPERFIL_PASS = "NoPerfil@123"


@pytest.fixture
def user_noperfil(db, perfis):
    """Usuário sem perfis para testes de /me/perfis."""
    u = User(email=NOPERFIL_EMAIL, hashed_password=get_password_hash(NOPERFIL_PASS))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def headers_noperfil(client, user_noperfil):
    res = client.post("/auth/login", data={"username": NOPERFIL_EMAIL, "password": NOPERFIL_PASS})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


class TestPerfis:
    def test_listar_perfis_usuario_sem_perfis(self, client, headers_noperfil):
        res = client.get("/me/perfis", headers=headers_noperfil)
        assert res.status_code == 200
        assert res.json() == []

    def test_listar_perfis_com_perfil_atribuido(self, client, headers_noperfil, db, user_noperfil):
        p = db.query(Perfil).filter(Perfil.nome == "mercado").first()
        user_noperfil.perfis.append(p)
        db.commit()

        res = client.get("/me/perfis", headers=headers_noperfil)
        assert res.status_code == 200
        assert "mercado" in res.json()

    def test_listar_perfis_sem_auth(self, client):
        res = client.get("/me/perfis")
        assert res.status_code == 401

    def test_perfis_isolados_entre_usuarios(self, client, auth_headers, headers_noperfil, db, user_noperfil):
        res = client.get("/me/perfis", headers=headers_noperfil)
        assert res.json() == []

        res2 = client.get("/me/perfis", headers=auth_headers)
        assert len(res2.json()) > 0

    def test_usuario_com_todos_perfis(self, client, auth_headers):
        res = client.get("/me/perfis", headers=auth_headers)
        perfis = res.json()
        assert "automacao_financeira" in perfis
        assert "gerenciador_credenciais" in perfis
        assert "combustivel" in perfis
