"""
Migração: adiciona coluna 'competencia' na tabela contas.
Execute uma vez: python migrar_competencia.py
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrada no ambiente.")

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # Verifica se a coluna já existe antes de criar
    result = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'contas' AND column_name = 'competencia'
    """))
    if result.fetchone():
        print("Coluna 'competencia' já existe — nada a fazer.")
    else:
        conn.execute(text("ALTER TABLE contas ADD COLUMN competencia VARCHAR"))
        conn.commit()
        print("Coluna 'competencia' adicionada com sucesso!")
