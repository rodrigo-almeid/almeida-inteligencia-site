"""
Testes de controle de acesso (RBAC).
Valida que rotas protegidas retornam 403 quando o usuário não possui o perfil exigido.
"""
import pytest
from backend.core.models import User, Perfil
from backend.core.security import get_password_hash

RBAC_EMAIL = "sem_perfil@teste.com"
RBAC_PASS = "SemPerfil@123"

PARCIAL_EMAIL = "parcial@teste.com"
PARCIAL_PASS = "Parcial@123"


@pytest.fixture
def user_sem_perfil(db, perfis):
    """Usuário sem nenhum perfil RBAC atribuído."""
    u = User(email=RBAC_EMAIL, hashed_password=get_password_hash(RBAC_PASS))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def headers_sem_perfil(client, user_sem_perfil):
    res = client.post("/auth/login", data={"username": RBAC_EMAIL, "password": RBAC_PASS})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def user_so_dashboard(db, perfis):
    """Usuário com apenas o perfil 'dashboard'."""
    u = User(email=PARCIAL_EMAIL, hashed_password=get_password_hash(PARCIAL_PASS))
    db.add(u)
    db.commit()
    db.refresh(u)
    p = db.query(Perfil).filter(Perfil.nome == "dashboard").first()
    u.perfis.append(p)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def headers_so_dashboard(client, user_so_dashboard):
    res = client.post("/auth/login", data={"username": PARCIAL_EMAIL, "password": PARCIAL_PASS})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# ──────────────────────────────────────────────────────────────────
# Usuário SEM NENHUM perfil → 403 em TODAS as rotas protegidas
# ──────────────────────────────────────────────────────────────────

class TestSemPerfil:
    """Usuário sem perfis deve receber 403 em todas as rotas protegidas."""

    def test_categorias_get(self, client, headers_sem_perfil):
        res = client.get("/categorias/", headers=headers_sem_perfil)
        assert res.status_code == 403

    def test_categorias_post(self, client, headers_sem_perfil):
        res = client.post("/categorias/", json={"nome": "Teste"}, headers=headers_sem_perfil)
        assert res.status_code == 403

    def test_contas_get(self, client, headers_sem_perfil):
        res = client.get("/contas/", headers=headers_sem_perfil)
        assert res.status_code == 403

    def test_contas_post(self, client, headers_sem_perfil):
        res = client.post("/contas/", json={
            "descricao": "Teste", "vencimento": "2026-07-15", "valor": 100
        }, headers=headers_sem_perfil)
        assert res.status_code == 403

    def test_dividas_get(self, client, headers_sem_perfil):
        res = client.get("/dividas/", headers=headers_sem_perfil)
        assert res.status_code == 403

    def test_pessoas_get(self, client, headers_sem_perfil):
        res = client.get("/pessoas/", headers=headers_sem_perfil)
        assert res.status_code == 403

    def test_senhas_post(self, client, headers_sem_perfil):
        res = client.post("/me/senhas/", json={
            "sistema": "X", "usuario_sistema": "u", "senha": "s", "pessoa_id": 1
        }, headers=headers_sem_perfil)
        assert res.status_code == 403

    def test_abastecimentos_get(self, client, headers_sem_perfil):
        res = client.get("/abastecimentos/", headers=headers_sem_perfil)
        assert res.status_code == 403

    def test_mercado_get(self, client, headers_sem_perfil):
        res = client.get("/mercado/compras", headers=headers_sem_perfil)
        assert res.status_code == 403

    def test_mensagem_erro_contém_perfil(self, client, headers_sem_perfil):
        res = client.get("/categorias/", headers=headers_sem_perfil)
        assert "dashboard" in res.json()["detail"]


# ──────────────────────────────────────────────────────────────────
# Usuário COM perfil 'dashboard' → acessa financeiro, bloqueado no resto
# ──────────────────────────────────────────────────────────────────

class TestPerfilParcial:
    """Usuário com perfil 'dashboard' acessa rotas financeiras mas não credenciais/combustível."""

    def test_categorias_ok(self, client, headers_so_dashboard):
        res = client.get("/categorias/", headers=headers_so_dashboard)
        assert res.status_code == 200

    def test_contas_ok(self, client, headers_so_dashboard):
        res = client.get("/contas/", headers=headers_so_dashboard)
        assert res.status_code == 200

    def test_dividas_ok(self, client, headers_so_dashboard):
        res = client.get("/dividas/", headers=headers_so_dashboard)
        assert res.status_code == 200

    def test_pessoas_bloqueado(self, client, headers_so_dashboard):
        res = client.get("/pessoas/", headers=headers_so_dashboard)
        assert res.status_code == 403
        assert "senhas" in res.json()["detail"]

    def test_senhas_bloqueado(self, client, headers_so_dashboard):
        res = client.post("/me/senhas/", json={
            "sistema": "X", "usuario_sistema": "u", "senha": "s", "pessoa_id": 1
        }, headers=headers_so_dashboard)
        assert res.status_code == 403

    def test_abastecimentos_bloqueado(self, client, headers_so_dashboard):
        res = client.get("/abastecimentos/", headers=headers_so_dashboard)
        assert res.status_code == 403
        assert "abastecimento" in res.json()["detail"]

    def test_mercado_bloqueado(self, client, headers_so_dashboard):
        res = client.get("/mercado/compras", headers=headers_so_dashboard)
        assert res.status_code == 403
        assert "financeiro" in res.json()["detail"]


# ──────────────────────────────────────────────────────────────────
# Rotas públicas (auth) devem continuar acessíveis
# ──────────────────────────────────────────────────────────────────

class TestRotasPublicas:
    """Rotas de auth não exigem perfil."""

    def test_register(self, client):
        res = client.post("/auth/register", json={
            "email": "publico@teste.com", "password": "Pub@12345"
        })
        assert res.status_code == 201

    def test_login(self, client, user_sem_perfil):
        res = client.post("/auth/login", data={
            "username": RBAC_EMAIL, "password": RBAC_PASS
        })
        assert res.status_code == 200
        assert "access_token" in res.json()

    def test_listar_perfis(self, client, headers_sem_perfil):
        res = client.get("/me/perfis", headers=headers_sem_perfil)
        assert res.status_code == 200
        assert res.json() == []


# ──────────────────────────────────────────────────────────────────
# Endpoint de atribuição de perfis
# ──────────────────────────────────────────────────────────────────

class TestAtribuirPerfis:
    """Testa o endpoint /auth/perfis/atribuir."""

    def test_atribuir_perfil(self, client, auth_headers, user_sem_perfil):
        res = client.post("/auth/perfis/atribuir", json={
            "email": RBAC_EMAIL, "perfis": ["dashboard"]
        }, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["perfis"] == ["dashboard"]

    def test_usuario_com_perfil_acessa_rota(self, client, auth_headers, user_sem_perfil):
        client.post("/auth/perfis/atribuir", json={
            "email": RBAC_EMAIL, "perfis": ["dashboard"]
        }, headers=auth_headers)
        headers = {"Authorization": f"Bearer {client.post('/auth/login', data={'username': RBAC_EMAIL, 'password': RBAC_PASS}).json()['access_token']}"}
        res = client.get("/categorias/", headers=headers)
        assert res.status_code == 200

    def test_perfil_invalido(self, client, auth_headers, user_sem_perfil):
        res = client.post("/auth/perfis/atribuir", json={
            "email": RBAC_EMAIL, "perfis": ["inexistente"]
        }, headers=auth_headers)
        assert res.status_code == 400

    def test_usuario_inexistente(self, client, auth_headers):
        res = client.post("/auth/perfis/atribuir", json={
            "email": "nao_existe@teste.com", "perfis": ["dashboard"]
        }, headers=auth_headers)
        assert res.status_code == 404
