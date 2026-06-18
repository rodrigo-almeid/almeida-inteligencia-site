"""Testes do módulo de autenticação: /auth/register e /auth/login."""
import pytest
from .conftest import USER_EMAIL, USER_PASS


# ─── Register ────────────────────────────────────────────────────────

class TestRegister:
    def test_register_success(self, client):
        res = client.post("/auth/register", json={"email": "novo@teste.com", "password": "Senha123!"})
        assert res.status_code == 201
        assert "sucesso" in res.json()["message"].lower()

    def test_register_cria_pessoa_default(self, client, db):
        from backend.core.models import Pessoa
        client.post("/auth/register", json={"email": "p@teste.com", "password": "Abc@1234"})
        db.expire_all()
        p = db.query(Pessoa).filter_by(principal=True).first()
        assert p is not None
        assert p.nome == "Meu Perfil"

    def test_register_email_duplicado(self, client, user):
        res = client.post("/auth/register", json={"email": USER_EMAIL, "password": "OutraSenha@1"})
        assert res.status_code == 400
        assert "já cadastrado" in res.json()["detail"].lower()

    def test_register_email_invalido(self, client):
        res = client.post("/auth/register", json={"email": "nao-e-email", "password": "Abc@1234"})
        assert res.status_code == 422

    def test_register_sem_senha(self, client):
        res = client.post("/auth/register", json={"email": "ok@teste.com"})
        assert res.status_code == 422

    def test_register_sem_email(self, client):
        res = client.post("/auth/register", json={"password": "Abc@1234"})
        assert res.status_code == 422


# ─── Login ───────────────────────────────────────────────────────────

class TestLogin:
    def test_login_success(self, client, user):
        res = client.post("/auth/login", data={"username": USER_EMAIL, "password": USER_PASS})
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_senha_errada(self, client, user):
        res = client.post("/auth/login", data={"username": USER_EMAIL, "password": "WrongPass!"})
        assert res.status_code == 400
        assert "inválid" in res.json()["detail"].lower()

    def test_login_email_inexistente(self, client):
        res = client.post("/auth/login", data={"username": "naoexiste@teste.com", "password": "Abc@1234"})
        assert res.status_code == 400

    def test_login_sem_campos(self, client):
        res = client.post("/auth/login", data={})
        assert res.status_code == 422

    def test_token_gerado_e_valido(self, client, user):
        """Token retornado deve ser aceito em endpoints protegidos."""
        res = client.post("/auth/login", data={"username": USER_EMAIL, "password": USER_PASS})
        token = res.json()["access_token"]
        res2 = client.get("/pessoas/", headers={"Authorization": f"Bearer {token}"})
        assert res2.status_code == 200

    def test_endpoint_protegido_sem_token(self, client):
        res = client.get("/pessoas/")
        assert res.status_code == 401

    def test_endpoint_protegido_token_invalido(self, client):
        res = client.get("/pessoas/", headers={"Authorization": "Bearer token.invalido.aqui"})
        assert res.status_code == 401


# ─── SSO ─────────────────────────────────────────────────────────────

class TestSSO:
    PORTAL_KEY = "test-portal-secret-key"

    def _make_token(self, email: str) -> str:
        from jose import jwt
        return jwt.encode({"email": email}, self.PORTAL_KEY, algorithm="HS256")

    def test_sso_cria_usuario_novo(self, client, db):
        from backend.core.models import User
        token = self._make_token("sso_novo@teste.com")
        res = client.post("/auth/sso", json={"portal_token": token})
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["email"] == "sso_novo@teste.com"
        db.expire_all()
        assert db.query(User).filter(User.email == "sso_novo@teste.com").first() is not None

    def test_sso_login_usuario_existente(self, client, user):
        token = self._make_token(user.email)
        res = client.post("/auth/sso", json={"portal_token": token})
        assert res.status_code == 200
        assert res.json()["email"] == user.email

    def test_sso_token_invalido(self, client):
        res = client.post("/auth/sso", json={"portal_token": "token.invalido"})
        assert res.status_code == 401

    def test_sso_token_sem_email(self, client):
        from jose import jwt
        token = jwt.encode({"sub": "sem_email"}, self.PORTAL_KEY, algorithm="HS256")
        res = client.post("/auth/sso", json={"portal_token": token})
        assert res.status_code == 401
