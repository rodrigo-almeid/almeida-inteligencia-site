import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Ele tenta ler o .env local. Se não achar (porque está no Docker), não tem problema!
load_dotenv()

# Puxa a variável que o Docker injetou automaticamente na memória
DATABASE_URL = os.getenv("DATABASE_URL")

# O seu print de segurança continua aqui, perfeito!
if DATABASE_URL is None:  # pragma: no cover
    print("ERRO: A variável DATABASE_URL não foi encontrada no ambiente!")
else:
    print("Sucesso: DATABASE_URL carregada do ambiente Docker!")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():  # pragma: no cover
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()