"""
Testes completos de controle de acesso (RBAC).
Testa todas as combinações de perfil × rota para garantir que:
- Sem perfil → 403 em tudo
- Com perfil específico → acessa só suas rotas, 403 no resto
- Com múltiplos perfis → acessa a união das rotas
"""
import pytest
from backend.core.models import User, Perfil
from backend.core.security import get_password_hash


# ──────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────

def _create_user_with_perfis(db, perfis_list, email, password):
    u = User(email=email, hashed_password=get_password_hash(password))
    db.add(u)
    db.commit()
    db.refresh(u)
    for nome in perfis_list:
        p = db.query(Perfil).filter(Perfil.nome == nome).first()
        if p:
            u.perfis.append(p)
    db.commit()
    db.refresh(u)
    return u


def _login(client, email, password):
    res = client.post("/auth/login", data={"username": email, "password": password})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# Usuário sem perfil
@pytest.fixture
def user_sem_perfil(db, perfis):
    return _create_user_with_perfis(db, [], "sem_perfil@teste.com", "Sem@123")

@pytest.fixture
def h_sem_perfil(client, user_sem_perfil):
    return _login(client, "sem_perfil@teste.com", "Sem@123")


# Usuário só dashboard
@pytest.fixture
def user_dashboard(db, perfis):
    return _create_user_with_perfis(db, ["automacao_financeira"], "dashboard@teste.com", "Dash@123")

@pytest.fixture
def h_dashboard(client, user_dashboard):
    return _login(client, "dashboard@teste.com", "Dash@123")


# Usuário só senhas
@pytest.fixture
def user_senhas(db, perfis):
    return _create_user_with_perfis(db, ["gerenciador_credenciais"], "senhas@teste.com", "Senhas@123")

@pytest.fixture
def h_senhas(client, user_senhas):
    return _login(client, "senhas@teste.com", "Senhas@123")


# Usuário só abastecimento
@pytest.fixture
def user_abastecimento(db, perfis):
    return _create_user_with_perfis(db, ["combustivel"], "abast@teste.com", "Abast@123")

@pytest.fixture
def h_abastecimento(client, user_abastecimento):
    return _login(client, "abast@teste.com", "Abast@123")


# Usuário só financeiro (mercado)
@pytest.fixture
def user_financeiro(db, perfis):
    return _create_user_with_perfis(db, ["mercado"], "financeiro@teste.com", "Fin@123")

@pytest.fixture
def h_financeiro(client, user_financeiro):
    return _login(client, "financeiro@teste.com", "Fin@123")


# Usuário dashboard + senhas
@pytest.fixture
def user_dash_senhas(db, perfis):
    return _create_user_with_perfis(db, ["automacao_financeira", "gerenciador_credenciais"], "ds@teste.com", "DS@123")

@pytest.fixture
def h_dash_senhas(client, user_dash_senhas):
    return _login(client, "ds@teste.com", "DS@123")


# Usuário dashboard + abastecimento
@pytest.fixture
def user_dash_abast(db, perfis):
    return _create_user_with_perfis(db, ["automacao_financeira", "combustivel"], "da@teste.com", "DA@123")

@pytest.fixture
def h_dash_abast(client, user_dash_abast):
    return _login(client, "da@teste.com", "DA@123")


# ──────────────────────────────────────────────────────────────────
# Rotas de teste por módulo
# ──────────────────────────────────────────────────────────────────

ROTAS_DASHBOARD = [
    ("GET", "/categorias/"),
    ("GET", "/contas/"),
    ("GET", "/dividas/"),
]

ROTAS_SENHAS = [
    ("GET", "/pessoas/"),
]

ROTAS_ABASTECIMENTO = [
    ("GET", "/abastecimentos/"),
]

ROTAS_FINANCEIRO = [
    ("GET", "/mercado/compras"),
]

TODAS_ROTAS = ROTAS_DASHBOARD + ROTAS_SENHAS + ROTAS_ABASTECIMENTO + ROTAS_FINANCEIRO


# ──────────────────────────────────────────────────────────────────
# 1. Sem perfil → 403 em TUDO
# ──────────────────────────────────────────────────────────────────

class TestSemPerfil:
    @pytest.mark.parametrize("method,path", TODAS_ROTAS)
    def test_403_em_todas_rotas(self, client, h_sem_perfil, method, path):
        res = client.request(method, path, headers=h_sem_perfil)
        assert res.status_code == 403, f"{method} {path} retornou {res.status_code}, esperado 403"

    def test_mensagem_dashboard(self, client, h_sem_perfil):
        res = client.get("/categorias/", headers=h_sem_perfil)
        assert "automacao_financeira" in res.json()["detail"]

    def test_mensagem_credenciais(self, client, h_sem_perfil):
        res = client.get("/pessoas/", headers=h_sem_perfil)
        assert "gerenciador_credenciais" in res.json()["detail"]

    def test_mensagem_combustivel(self, client, h_sem_perfil):
        res = client.get("/abastecimentos/", headers=h_sem_perfil)
        assert "combustivel" in res.json()["detail"]

    def test_mensagem_mercado(self, client, h_sem_perfil):
        res = client.get("/mercado/compras", headers=h_sem_perfil)
        assert "mercado" in res.json()["detail"]

    def test_post_categoria_403(self, client, h_sem_perfil):
        res = client.post("/categorias/", json={"nome": "X"}, headers=h_sem_perfil)
        assert res.status_code == 403

    def test_post_conta_403(self, client, h_sem_perfil):
        res = client.post("/contas/", json={
            "descricao": "X", "vencimento": "2026-07-15", "valor": 100
        }, headers=h_sem_perfil)
        assert res.status_code == 403

    def test_post_pessoa_403(self, client, h_sem_perfil):
        res = client.post("/pessoas/", json={"nome": "X"}, headers=h_sem_perfil)
        assert res.status_code == 403

    def test_post_senha_403(self, client, h_sem_perfil):
        res = client.post("/me/senhas/", json={
            "sistema": "X", "usuario_sistema": "u", "senha": "s", "pessoa_id": 1
        }, headers=h_sem_perfil)
        assert res.status_code == 403

    def test_post_abastecimento_403(self, client, h_sem_perfil):
        res = client.post("/abastecimentos/", json={
            "data": "2026-07-01", "tipo_combustivel": "gasolina",
            "km_atual": 50000, "litros": 40, "valor_unitario": 5.89,
            "valor_total": 235.60, "forma_pagamento": "credito", "tanque_cheio": True
        }, headers=h_sem_perfil)
        assert res.status_code == 403


# ──────────────────────────────────────────────────────────────────
# 2. Só dashboard → financeiro OK, resto 403
# ──────────────────────────────────────────────────────────────────

class TestSoDashboard:
    @pytest.mark.parametrize("method,path", ROTAS_DASHBOARD)
    def test_200_rotas_financeiras(self, client, h_dashboard, method, path):
        res = client.request(method, path, headers=h_dashboard)
        assert res.status_code == 200, f"{method} {path} retornou {res.status_code}, esperado 200"

    @pytest.mark.parametrize("method,path", ROTAS_SENHAS)
    def test_403_rotas_senhas(self, client, h_dashboard, method, path):
        res = client.request(method, path, headers=h_dashboard)
        assert res.status_code == 403

    @pytest.mark.parametrize("method,path", ROTAS_ABASTECIMENTO)
    def test_403_rotas_abastecimento(self, client, h_dashboard, method, path):
        res = client.request(method, path, headers=h_dashboard)
        assert res.status_code == 403

    @pytest.mark.parametrize("method,path", ROTAS_FINANCEIRO)
    def test_403_rotas_mercado(self, client, h_dashboard, method, path):
        res = client.request(method, path, headers=h_dashboard)
        assert res.status_code == 403

    def test_criar_categoria_ok(self, client, h_dashboard):
        res = client.post("/categorias/", json={"nome": "Cat Dash"}, headers=h_dashboard)
        assert res.status_code in (200, 201)

    def test_criar_conta_ok(self, client, h_dashboard):
        res = client.post("/contas/", json={
            "descricao": "Conta Dash", "vencimento": "2026-07-15", "valor": 100
        }, headers=h_dashboard)
        assert res.status_code in (200, 201)


# ──────────────────────────────────────────────────────────────────
# 3. Só senhas → credenciais OK, resto 403
# ──────────────────────────────────────────────────────────────────

class TestSoSenhas:
    @pytest.mark.parametrize("method,path", ROTAS_SENHAS)
    def test_200_rotas_credenciais(self, client, h_senhas, method, path):
        res = client.request(method, path, headers=h_senhas)
        assert res.status_code == 200

    @pytest.mark.parametrize("method,path", ROTAS_DASHBOARD)
    def test_403_rotas_financeiras(self, client, h_senhas, method, path):
        res = client.request(method, path, headers=h_senhas)
        assert res.status_code == 403

    @pytest.mark.parametrize("method,path", ROTAS_ABASTECIMENTO)
    def test_403_rotas_abastecimento(self, client, h_senhas, method, path):
        res = client.request(method, path, headers=h_senhas)
        assert res.status_code == 403

    def test_criar_pessoa_ok(self, client, h_senhas):
        res = client.post("/pessoas/", json={"nome": "Perfil Senhas"}, headers=h_senhas)
        assert res.status_code in (200, 201)

    def test_criar_categoria_403(self, client, h_senhas):
        res = client.post("/categorias/", json={"nome": "X"}, headers=h_senhas)
        assert res.status_code == 403


# ──────────────────────────────────────────────────────────────────
# 4. Só abastecimento → combustível OK, resto 403
# ──────────────────────────────────────────────────────────────────

class TestSoAbastecimento:
    @pytest.mark.parametrize("method,path", ROTAS_ABASTECIMENTO)
    def test_200_rotas_combustivel(self, client, h_abastecimento, method, path):
        res = client.request(method, path, headers=h_abastecimento)
        assert res.status_code == 200

    @pytest.mark.parametrize("method,path", ROTAS_DASHBOARD)
    def test_403_rotas_financeiras(self, client, h_abastecimento, method, path):
        res = client.request(method, path, headers=h_abastecimento)
        assert res.status_code == 403

    @pytest.mark.parametrize("method,path", ROTAS_SENHAS)
    def test_403_rotas_credenciais(self, client, h_abastecimento, method, path):
        res = client.request(method, path, headers=h_abastecimento)
        assert res.status_code == 403

    def test_registrar_abastecimento_ok(self, client, h_abastecimento):
        res = client.post("/abastecimentos/", json={
            "data": "2026-07-01", "tipo_combustivel": "gasolina",
            "km_atual": 50000, "litros": 40, "valor_unitario": 5.89,
            "valor_total": 235.60, "forma_pagamento": "credito", "tanque_cheio": True
        }, headers=h_abastecimento)
        assert res.status_code in (200, 201)

    def test_criar_categoria_403(self, client, h_abastecimento):
        res = client.post("/categorias/", json={"nome": "X"}, headers=h_abastecimento)
        assert res.status_code == 403


# ──────────────────────────────────────────────────────────────────
# 5. Só financeiro → mercado OK, resto 403
# ──────────────────────────────────────────────────────────────────

class TestSoFinanceiro:
    @pytest.mark.parametrize("method,path", ROTAS_FINANCEIRO)
    def test_200_rotas_mercado(self, client, h_financeiro, method, path):
        res = client.request(method, path, headers=h_financeiro)
        assert res.status_code == 200

    @pytest.mark.parametrize("method,path", ROTAS_DASHBOARD)
    def test_403_rotas_financeiras(self, client, h_financeiro, method, path):
        res = client.request(method, path, headers=h_financeiro)
        assert res.status_code == 403

    @pytest.mark.parametrize("method,path", ROTAS_SENHAS)
    def test_403_rotas_credenciais(self, client, h_financeiro, method, path):
        res = client.request(method, path, headers=h_financeiro)
        assert res.status_code == 403

    @pytest.mark.parametrize("method,path", ROTAS_ABASTECIMENTO)
    def test_403_rotas_abastecimento(self, client, h_financeiro, method, path):
        res = client.request(method, path, headers=h_financeiro)
        assert res.status_code == 403


# ──────────────────────────────────────────────────────────────────
# 6. Dashboard + Senhas → financeiro + credenciais OK, combustível 403
# ──────────────────────────────────────────────────────────────────

class TestDashboardMaisSenhas:
    @pytest.mark.parametrize("method,path", ROTAS_DASHBOARD + ROTAS_SENHAS)
    def test_200_rotas_permitidas(self, client, h_dash_senhas, method, path):
        res = client.request(method, path, headers=h_dash_senhas)
        assert res.status_code == 200, f"{method} {path} retornou {res.status_code}"

    @pytest.mark.parametrize("method,path", ROTAS_ABASTECIMENTO)
    def test_403_abastecimento(self, client, h_dash_senhas, method, path):
        res = client.request(method, path, headers=h_dash_senhas)
        assert res.status_code == 403

    @pytest.mark.parametrize("method,path", ROTAS_FINANCEIRO)
    def test_403_mercado(self, client, h_dash_senhas, method, path):
        res = client.request(method, path, headers=h_dash_senhas)
        assert res.status_code == 403


# ──────────────────────────────────────────────────────────────────
# 7. Dashboard + Abastecimento → financeiro + combustível OK
# ──────────────────────────────────────────────────────────────────

class TestDashboardMaisAbastecimento:
    @pytest.mark.parametrize("method,path", ROTAS_DASHBOARD + ROTAS_ABASTECIMENTO)
    def test_200_rotas_permitidas(self, client, h_dash_abast, method, path):
        res = client.request(method, path, headers=h_dash_abast)
        assert res.status_code == 200, f"{method} {path} retornou {res.status_code}"

    @pytest.mark.parametrize("method,path", ROTAS_SENHAS)
    def test_403_credenciais(self, client, h_dash_abast, method, path):
        res = client.request(method, path, headers=h_dash_abast)
        assert res.status_code == 403

    @pytest.mark.parametrize("method,path", ROTAS_FINANCEIRO)
    def test_403_mercado(self, client, h_dash_abast, method, path):
        res = client.request(method, path, headers=h_dash_abast)
        assert res.status_code == 403


# ──────────────────────────────────────────────────────────────────
# 8. Rotas públicas → acessíveis sem perfil
# ──────────────────────────────────────────────────────────────────

class TestRotasPublicas:
    def test_register(self, client):
        res = client.post("/auth/register", json={"email": "pub@teste.com", "password": "Pub@12345"})
        assert res.status_code == 201

    def test_login(self, client, user_sem_perfil):
        res = client.post("/auth/login", data={"username": "sem_perfil@teste.com", "password": "Sem@123"})
        assert res.status_code == 200

    def test_listar_perfis_vazio(self, client, h_sem_perfil):
        res = client.get("/me/perfis", headers=h_sem_perfil)
        assert res.status_code == 200
        assert res.json() == []

    def test_listar_perfis_com_dashboard(self, client, h_dashboard):
        res = client.get("/me/perfis", headers=h_dashboard)
        assert res.status_code == 200
        assert "automacao_financeira" in res.json()

    def test_listar_perfis_multiplos(self, client, h_dash_senhas):
        res = client.get("/me/perfis", headers=h_dash_senhas)
        perfis = res.json()
        assert "automacao_financeira" in perfis
        assert "gerenciador_credenciais" in perfis


# ──────────────────────────────────────────────────────────────────
# 9. Endpoint de atribuição de perfis — DESATIVADO (2026-07-09)
#
# Não validava se quem chama é admin — qualquer usuário autenticado podia se
# auto-atribuir qualquer perfil do sistema. Desativado até decidirmos o modelo
# de autorização certo. Os testes do comportamento antigo estão no histórico
# do git (mesmo commit que desativou o endpoint em perfis.py); restaurar
# quando o endpoint for reativado com a checagem de admin.
# ──────────────────────────────────────────────────────────────────

class TestAtribuirPerfisDesativado:
    def test_atribuir_retorna_403(self, client, auth_headers, user_sem_perfil):
        res = client.post("/auth/perfis/atribuir", json={
            "email": "sem_perfil@teste.com", "perfis": ["automacao_financeira"]
        }, headers=auth_headers)
        assert res.status_code == 403

    def test_atribuir_nao_altera_perfis(self, client, auth_headers, user_sem_perfil, db):
        client.post("/auth/perfis/atribuir", json={
            "email": "sem_perfil@teste.com", "perfis": ["automacao_financeira"]
        }, headers=auth_headers)
        db.expire_all()
        u = db.query(User).filter(User.email == "sem_perfil@teste.com").first()
        assert u.perfis == []


# ──────────────────────────────────────────────────────────────────
# 10. Token inválido / sem token → 401
# ──────────────────────────────────────────────────────────────────

class TestSemAutenticacao:
    @pytest.mark.parametrize("method,path", TODAS_ROTAS)
    def test_401_sem_token(self, client, method, path):
        res = client.request(method, path)
        assert res.status_code in (401, 403)

    @pytest.mark.parametrize("method,path", TODAS_ROTAS)
    def test_401_token_invalido(self, client, method, path):
        res = client.request(method, path, headers={"Authorization": "Bearer token.invalido.aqui"})
        assert res.status_code == 401
