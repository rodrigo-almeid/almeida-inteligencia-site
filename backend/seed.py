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

# Tabela de usuários
cur.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(150) NOT NULL,
    email       VARCHAR(150) UNIQUE NOT NULL,
    senha_hash  TEXT NOT NULL,
    perfil_id   INTEGER,
    ativo       BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em   TIMESTAMP DEFAULT NOW()
)
""")

# Tabela de perfis
cur.execute("""
CREATE TABLE IF NOT EXISTS perfis (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(100) UNIQUE NOT NULL,
    slug        VARCHAR(100) UNIQUE NOT NULL,
    descricao   TEXT DEFAULT '',
    criado_em   TIMESTAMP DEFAULT NOW()
)
""")

# Tabela de menus por perfil
cur.execute("""
CREATE TABLE IF NOT EXISTS perfil_menus (
    id          SERIAL PRIMARY KEY,
    perfil_id   INTEGER NOT NULL REFERENCES perfis(id) ON DELETE CASCADE,
    menu_slug   VARCHAR(100) NOT NULL
)
""")

# Perfil admin (slug fixo usado no token)
cur.execute("""
INSERT INTO perfis (nome, slug, descricao)
VALUES ('Administrador', 'admin', 'Acesso total ao sistema')
ON CONFLICT (slug) DO NOTHING
""")

conn.commit()

# Busca id do perfil admin
cur.execute("SELECT id FROM perfis WHERE slug = 'admin'")
admin_perfil_id = cur.fetchone()[0]

# Usuário admin
senha_hash = bcrypt.hashpw(b"REDACTED", bcrypt.gensalt(12)).decode()
cur.execute("""
INSERT INTO usuarios (nome, email, senha_hash, perfil_id)
VALUES (%s, %s, %s, %s)
ON CONFLICT (email) DO NOTHING
""", ("Almeida Admin", "almeidainteligencia@gmail.com", senha_hash, admin_perfil_id))

conn.commit()
conn.close()
print("Banco inicializado com sucesso.")
print("Admin: almeidainteligencia@gmail.com / REDACTED")
