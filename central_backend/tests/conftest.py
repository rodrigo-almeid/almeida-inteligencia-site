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
os.environ["TESTING"] = "1"
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
from backend.core.models import (
    Base, User, Perfil, Pessoa, Conta, Senha, AssistenteConfig,
    AgendamentoConfig, HorarioFuncionamento, Service, Client, Appointment,
    ConversationMessage, LlmLog,
)
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


ALL_PERFIS = ["dashboard", "senhas", "abastecimento", "games", "credenciais", "financeiro"]


@pytest.fixture
def perfis(db):
    """Cria todos os perfis RBAC no banco de testes."""
    objs = []
    for nome in ALL_PERFIS:
        p = db.query(Perfil).filter(Perfil.nome == nome).first()
        if not p:
            p = Perfil(nome=nome)
            db.add(p)
        objs.append(p)
    db.commit()
    for p in objs:
        db.refresh(p)
    return objs


@pytest.fixture
def user(db, perfis):
    """Usuário autenticado principal — com todos os perfis."""
    u = User(email=USER_EMAIL, hashed_password=get_password_hash(USER_PASS))
    db.add(u)
    db.commit()
    db.refresh(u)
    for p in perfis:
        u.perfis.append(p)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def user2(db, perfis):
    """Segundo usuário — para testes de isolamento, com todos os perfis."""
    u = User(email=USER2_EMAIL, hashed_password=get_password_hash(USER2_PASS))
    db.add(u)
    db.commit()
    db.refresh(u)
    for p in perfis:
        u.perfis.append(p)
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


# ─── Fixtures do Agendamento ─────────────────────────────────────────

@pytest.fixture
def agendamento_config(db, user):
    """Config de agendamento do usuário principal."""
    from backend.agendamento.crypto import encrypt_key
    cfg = AgendamentoConfig(
        user_id=user.id,
        whatsapp_token=encrypt_key("test-wa-token"),
        whatsapp_phone_id="123456789",
        whatsapp_verify_token="verify-test",
        gemini_api_key=encrypt_key("test-gemini-key"),
        groq_api_key=encrypt_key("test-groq-key"),
        ollama_url="http://localhost:11434",
        ollama_model="llama3",
        prioridade_llms='["gemini","groq","ollama"]',
        gemini_ativo=True,
        groq_ativo=True,
        ollama_ativo=False,
        catalogo_prompt="Somos o Salão Teste. Corte R$40.",
        mensagem_midia_bloqueada="Só texto, por favor.",
        mensagem_contingencia="Estamos indisponíveis.",
        ativo=True,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


@pytest.fixture
def agendamento_servico(db, agendamento_config):
    """Serviço de teste."""
    s = Service(
        nome="Corte Masculino",
        descricao="Corte simples",
        duracao_minutos=30,
        preco=40.0,
        ativo=True,
        config_id=agendamento_config.id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@pytest.fixture
def agendamento_horarios(db, agendamento_config):
    """Horários de seg a sáb, 09h-18h."""
    horarios = []
    for dia in range(6):
        h = HorarioFuncionamento(
            dia_semana=dia, hora_inicio="09:00", hora_fim="18:00",
            ativo=True, config_id=agendamento_config.id,
        )
        db.add(h)
        horarios.append(h)
    db.commit()
    for h in horarios:
        db.refresh(h)
    return horarios


@pytest.fixture
def agendamento_client(db, agendamento_config):
    """Cliente de teste do WhatsApp."""
    c = Client(
        telefone="5543999999999", nome="João Teste",
        config_id=agendamento_config.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def agendamento_appointment(db, agendamento_config, agendamento_client, agendamento_servico):
    """Agendamento confirmado de teste."""
    from datetime import datetime, timedelta
    amanha = datetime.utcnow().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
    a = Appointment(
        data_hora=amanha, status="confirmado",
        config_id=agendamento_config.id,
        client_id=agendamento_client.id,
        service_id=agendamento_servico.id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a
