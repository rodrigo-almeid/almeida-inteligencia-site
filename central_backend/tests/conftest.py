"""
Fixtures compartilhadas para todos os testes do central_backend.

IMPORTANTE: os.environ deve ser preenchido ANTES de qualquer import do backend,
pois senhas.py e security.py lêem env vars no nível de módulo.
"""
import os
from cryptography.fernet import Fernet

# ─── Env vars: ANTES de qualquer import do backend ───────────────────
_FERNET_KEY = Fernet.generate_key().decode()
os.environ.setdefault("FERNET_SECRET_KEY", _FERNET_KEY)
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-para-testes-unitarios!")
os.environ.setdefault("DATABASE_URL", "sqlite:///./central_test.db")
os.environ.setdefault("PORTAL_SECRET_KEY", "test-portal-secret-key")
# ─────────────────────────────────────────────────────────────────────

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Engine SQLite dedicada para testes (não usa a engine do database.py)
_TEST_ENGINE = create_engine(
    "sqlite:///./central_test.db",
    connect_args={"check_same_thread": False},
)
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_TEST_ENGINE)

# Imports do backend (só aqui, depois dos env vars)
from backend.core.models import Base, User, Pessoa, Conta, Senha, AssistenteConfig
from backend.core.database import get_db
from backend.core.security import get_password_hash
from backend.main import app

# Garante que as tabelas existam na engine de testes
Base.metadata.create_all(bind=_TEST_ENGINE)


# ─── Fixtures de banco ────────────────────────────────────────────────

@pytest.fixture(scope="function")
def db():
    """Sessão limpa por teste: apaga todos os dados após cada execução."""
    session = _TestSession()
    yield session
    session.rollback()
    # Limpa todas as tabelas em ordem reversa (respeita FK)
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()


@pytest.fixture(scope="function")
def client(db):
    """TestClient com get_db substituído pela sessão de teste."""
    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ─── Fixtures de dados ────────────────────────────────────────────────

USER_EMAIL = "usuario@teste.com"
USER_PASS = "Senha@Teste123"
USER2_EMAIL = "outro@teste.com"
USER2_PASS = "Outro@Teste456"


@pytest.fixture
def user(db):
    """Usuário autenticado principal."""
    u = User(email=USER_EMAIL, hashed_password=get_password_hash(USER_PASS))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def user2(db):
    """Segundo usuário — para testes de isolamento."""
    u = User(email=USER2_EMAIL, hashed_password=get_password_hash(USER2_PASS))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def auth_headers(client, user):
    """Headers de autenticação para o usuário principal."""
    res = client.post("/auth/login", data={"username": USER_EMAIL, "password": USER_PASS})
    assert res.status_code == 200, f"Login falhou: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers2(client, user2):
    """Headers de autenticação para o segundo usuário."""
    res = client.post("/auth/login", data={"username": USER2_EMAIL, "password": USER2_PASS})
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def pessoa(db, user):
    """Perfil/Pessoa do usuário principal."""
    p = Pessoa(nome="Perfil Pessoal", principal=True, user_id=user.id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture
def pessoa2(db, user2):
    """Perfil do segundo usuário."""
    p = Pessoa(nome="Perfil Outro", principal=True, user_id=user2.id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture
def conta(db, user):
    """Conta financeira do usuário principal."""
    from datetime import date
    c = Conta(
        descricao="Aluguel",
        vencimento=date(2025, 6, 10),
        valor=1500.0,
        natureza="despesa",
        status="pendente",
        tipo_recorrencia="mensal",
        user_id=user.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c
