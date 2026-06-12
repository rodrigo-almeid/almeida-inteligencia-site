"""
Testes do portal auth backend (psycopg2).

Como o backend usa psycopg2 puro (sem ORM), usamos mocking completo
para não depender de uma instância PostgreSQL rodando.
"""
import pytest
import bcrypt
import jwt
import os
from unittest.mock import patch, MagicMock, call
from fastapi.testclient import TestClient

os.environ.setdefault("SECRET_KEY", "test-secret-key-para-testes-unitarios")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")

from main import app, create_token, verify_token, SECRET_KEY

client = TestClient(app)

ADMIN_TOKEN = create_token(1, "admin@teste.com", "admin", [])
CLIENTE_TOKEN = create_token(2, "cliente@teste.com", "cliente", [])
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
CLIENTE_HEADERS = {"Authorization": f"Bearer {CLIENTE_TOKEN}"}


# ─── Helper para mockar cursor ────────────────────────────────────────

def make_cursor(fetchone=None, fetchall=None):
    cur = MagicMock()
    cur.fetchone.return_value = fetchone
    cur.fetchall.return_value = fetchall or []
    return cur


def make_conn(cur):
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


# ─── Health ──────────────────────────────────────────────────────────

def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


# ─── Token utils ─────────────────────────────────────────────────────

class TestToken:
    def test_create_token_contains_fields(self):
        token = create_token(42, "test@x.com", "admin", ["email"])
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        assert payload["sub"] == "42"
        assert payload["email"] == "test@x.com"
        assert payload["perfil"] == "admin"
        assert payload["sistemas"] == ["email"]

    def test_verify_token_invalido(self):
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token.invalido")
        with pytest.raises(HTTPException) as exc:
            verify_token(creds)
        assert exc.value.status_code == 401

    def test_verify_token_valido(self):
        from fastapi.security import HTTPAuthorizationCredentials
        token = create_token(1, "ok@test.com", "admin", [])
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        payload = verify_token(creds)
        assert payload["email"] == "ok@test.com"


# ─── Login ───────────────────────────────────────────────────────────

class TestLogin:
    def _mock_user(self, email="admin@teste.com", ativo=True, perfil_id=1):
        senha_hash = bcrypt.hashpw(b"Senha@123", bcrypt.gensalt()).decode()
        return {"id": 1, "email": email, "senha_hash": senha_hash, "ativo": ativo, "perfil_id": perfil_id, "nome": "Admin"}

    @patch("main.get_conn")
    def test_login_success(self, mock_get_conn):
        user = self._mock_user()
        cur = make_cursor(fetchone=user)
        cur.fetchone.side_effect = [user, {"slug": "admin"}, None]
        conn = make_conn(cur)
        mock_get_conn.return_value = conn

        res = client.post("/api/login", json={"email": "admin@teste.com", "senha": "Senha@123"})
        assert res.status_code == 200
        data = res.json()
        assert "token" in data
        assert data["email"] == "admin@teste.com"

    @patch("main.get_conn")
    def test_login_senha_errada(self, mock_get_conn):
        user = self._mock_user()
        cur = make_cursor(fetchone=user)
        conn = make_conn(cur)
        mock_get_conn.return_value = conn

        res = client.post("/api/login", json={"email": "admin@teste.com", "senha": "SenhaErrada"})
        assert res.status_code == 401

    @patch("main.get_conn")
    def test_login_usuario_nao_encontrado(self, mock_get_conn):
        cur = make_cursor(fetchone=None)
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.post("/api/login", json={"email": "nao@existe.com", "senha": "Abc@123"})
        assert res.status_code == 401

    @patch("main.get_conn")
    def test_login_usuario_inativo(self, mock_get_conn):
        user = self._mock_user(ativo=False)
        cur = make_cursor(fetchone=user)
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.post("/api/login", json={"email": "admin@teste.com", "senha": "Senha@123"})
        assert res.status_code == 403

    @patch("main.get_conn")
    def test_login_db_error(self, mock_get_conn):
        mock_get_conn.side_effect = Exception("Connection refused")
        res = client.post("/api/login", json={"email": "x@x.com", "senha": "abc"})
        assert res.status_code == 500

    def test_me_retorna_payload_token(self):
        res = client.get("/api/me", headers=ADMIN_HEADERS)
        assert res.status_code == 200
        assert res.json()["email"] == "admin@teste.com"

    def test_me_sem_token(self):
        res = client.get("/api/me")
        assert res.status_code == 403  # HTTPBearer retorna 403 se token ausente


# ─── Usuários ────────────────────────────────────────────────────────

class TestUsuarios:
    @patch("main.get_conn")
    def test_listar_usuarios_admin(self, mock_get_conn):
        cur = make_cursor(fetchall=[
            {"id": 1, "nome": "Admin", "email": "admin@x.com", "ativo": True,
             "criado_em": "2025-01-01", "perfil_id": 1, "perfil_nome": "Admin", "perfil_slug": "admin"}
        ])
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.get("/api/usuarios", headers=ADMIN_HEADERS)
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_listar_usuarios_nao_admin(self):
        res = client.get("/api/usuarios", headers=CLIENTE_HEADERS)
        assert res.status_code == 403

    def test_listar_usuarios_sem_auth(self):
        res = client.get("/api/usuarios")
        assert res.status_code == 403

    @patch("main.get_conn")
    def test_criar_usuario_success(self, mock_get_conn):
        cur = make_cursor(fetchone={"id": 10})
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.post("/api/usuarios", json={"nome": "Novo", "email": "novo@x.com", "senha": "Senha@1", "ativo": True}, headers=ADMIN_HEADERS)
        assert res.status_code == 201
        assert res.json()["id"] == 10

    @patch("main.get_conn")
    def test_criar_usuario_email_duplicado(self, mock_get_conn):
        import psycopg2
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.errors.UniqueViolation()
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.post("/api/usuarios", json={"nome": "N", "email": "dup@x.com", "senha": "S@1", "ativo": True}, headers=ADMIN_HEADERS)
        assert res.status_code == 409

    @patch("main.get_conn")
    def test_atualizar_usuario(self, mock_get_conn):
        cur = make_cursor(fetchone={"id": 1})
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.put("/api/usuarios/1", json={"nome": "Atualizado"}, headers=ADMIN_HEADERS)
        assert res.status_code == 200

    @patch("main.get_conn")
    def test_atualizar_usuario_inexistente(self, mock_get_conn):
        cur = make_cursor(fetchone=None)
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.put("/api/usuarios/99", json={"nome": "X"}, headers=ADMIN_HEADERS)
        assert res.status_code == 404

    @patch("main.get_conn")
    def test_deletar_usuario(self, mock_get_conn):
        cur = make_cursor(fetchone={"id": 1})
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.delete("/api/usuarios/1", headers=ADMIN_HEADERS)
        assert res.status_code == 200

    @patch("main.get_conn")
    def test_deletar_usuario_inexistente(self, mock_get_conn):
        cur = make_cursor(fetchone=None)
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.delete("/api/usuarios/99", headers=ADMIN_HEADERS)
        assert res.status_code == 404


# ─── Perfis ──────────────────────────────────────────────────────────

class TestPerfis:
    @patch("main.get_conn")
    def test_listar_perfis(self, mock_get_conn):
        cur = MagicMock()
        cur.fetchall.return_value = [{"id": 1, "nome": "Admin", "slug": "admin", "descricao": ""}]
        cur.fetchone.return_value = {"total": 2}
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.get("/api/perfis", headers=ADMIN_HEADERS)
        assert res.status_code == 200

    @patch("main.get_conn")
    def test_criar_perfil_success(self, mock_get_conn):
        cur = make_cursor(fetchone={"id": 5})
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.post("/api/perfis", json={"nome": "Gerente", "sistemas": []}, headers=ADMIN_HEADERS)
        assert res.status_code == 201

    @patch("main.get_conn")
    def test_criar_perfil_duplicado(self, mock_get_conn):
        import psycopg2
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.errors.UniqueViolation()
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.post("/api/perfis", json={"nome": "Admin"}, headers=ADMIN_HEADERS)
        assert res.status_code == 409

    @patch("main.get_conn")
    def test_atualizar_perfil(self, mock_get_conn):
        cur = make_cursor(fetchone={"id": 1, "nome": "Admin", "slug": "admin"})
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.put("/api/perfis/1", json={"nome": "Admin Atualizado"}, headers=ADMIN_HEADERS)
        assert res.status_code == 200

    @patch("main.get_conn")
    def test_deletar_perfil_com_usuarios(self, mock_get_conn):
        cur = make_cursor(fetchone={"total": 3})
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.delete("/api/perfis/1", headers=ADMIN_HEADERS)
        assert res.status_code == 400

    @patch("main.get_conn")
    def test_deletar_perfil_inexistente(self, mock_get_conn):
        cur = MagicMock()
        cur.fetchone.side_effect = [{"total": 0}, None]
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.delete("/api/perfis/99", headers=ADMIN_HEADERS)
        assert res.status_code == 404


# ─── Sistemas ────────────────────────────────────────────────────────

class TestSistemas:
    @patch("main.get_conn")
    def test_listar_sistemas(self, mock_get_conn):
        cur = make_cursor(fetchall=[{"id": 1, "nome": "Email", "slug": "email", "url": "/email/", "ativo": True, "descricao": "", "icone": "📧"}])
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.get("/api/sistemas", headers=ADMIN_HEADERS)
        assert res.status_code == 200

    @patch("main.get_conn")
    def test_criar_sistema(self, mock_get_conn):
        cur = make_cursor(fetchone={"id": 3})
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.post("/api/sistemas", json={"nome": "CRM", "slug": "crm", "url": "/crm/", "ativo": True}, headers=ADMIN_HEADERS)
        assert res.status_code == 201

    @patch("main.get_conn")
    def test_criar_sistema_slug_duplicado(self, mock_get_conn):
        import psycopg2
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.errors.UniqueViolation()
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.post("/api/sistemas", json={"nome": "Email2", "slug": "email", "url": "/email2/"}, headers=ADMIN_HEADERS)
        assert res.status_code == 409

    @patch("main.get_conn")
    def test_atualizar_sistema(self, mock_get_conn):
        cur = make_cursor(fetchone={"id": 1})
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.put("/api/sistemas/1", json={"nome": "Email Atualizado"}, headers=ADMIN_HEADERS)
        assert res.status_code == 200

    @patch("main.get_conn")
    def test_deletar_sistema(self, mock_get_conn):
        cur = make_cursor(fetchone={"id": 1})
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.delete("/api/sistemas/1", headers=ADMIN_HEADERS)
        assert res.status_code == 200

    @patch("main.get_conn")
    def test_deletar_sistema_inexistente(self, mock_get_conn):
        cur = make_cursor(fetchone=None)
        conn = make_conn(cur)
        mock_get_conn.return_value = conn
        res = client.delete("/api/sistemas/99", headers=ADMIN_HEADERS)
        assert res.status_code == 404

    def test_listar_sistemas_nao_admin(self):
        res = client.get("/api/sistemas", headers=CLIENTE_HEADERS)
        assert res.status_code == 403
