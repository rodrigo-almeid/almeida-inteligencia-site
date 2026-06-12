import bcrypt
import psycopg2
import os

DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "almeida")
DB_USER = os.getenv("DB_USER", "almeida")
DB_PASS = os.getenv("DB_PASS", "almeida123")

conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(150) NOT NULL,
    email       VARCHAR(150) UNIQUE NOT NULL,
    senha_hash  TEXT NOT NULL,
    perfil      VARCHAR(50) NOT NULL DEFAULT 'cliente',
    ativo       BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em   TIMESTAMP DEFAULT NOW()
)
""")

senha_hash = bcrypt.hashpw(b"REDACTED", bcrypt.gensalt(12)).decode()

cur.execute("""
INSERT INTO usuarios (nome, email, senha_hash, perfil)
VALUES (%s, %s, %s, %s)
ON CONFLICT (email) DO NOTHING
""", ("Almeida Admin", "almeidainteligencia@gmail.com", senha_hash, "admin"))

conn.commit()
conn.close()
print("Banco inicializado com sucesso.")
