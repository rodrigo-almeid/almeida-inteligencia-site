import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def _build_url() -> str:
    # Prioridade 1: DATABASE_URL explícita (definida pelo docker-compose ou manualmente)
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    # Prioridade 2: monta a partir de variáveis individuais (dev local sem Docker)
    host     = os.getenv("DB_HOST",     "localhost")
    port     = os.getenv("DB_PORT",     "5434")
    name     = os.getenv("DB_NAME",     "email_manager")
    user     = os.getenv("DB_USER",     "email_user")
    password = os.getenv("DB_PASSWORD", "troque_esta_senha")
    return f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}"


DATABASE_URL = _build_url()

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
