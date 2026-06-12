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
CREATE TABLE IF NOT EXISTS sistemas (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(150) NOT NULL,
    slug        VARCHAR(100) UNIQUE NOT NULL,
    descricao   TEXT DEFAULT '',
    url         TEXT NOT NULL,
    icone       VARCHAR(50) DEFAULT '🖥️',
    ativo       BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em   TIMESTAMP DEFAULT NOW()
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS perfis (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(100) UNIQUE NOT NULL,
    slug        VARCHAR(100) UNIQUE NOT NULL,
    descricao   TEXT DEFAULT '',
    criado_em   TIMESTAMP DEFAULT NOW()
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS perfil_sistemas (
    id          SERIAL PRIMARY KEY,
    perfil_id   INTEGER NOT NULL REFERENCES perfis(id) ON DELETE CASCADE,
    sistema_id  INTEGER NOT NULL REFERENCES sistemas(id) ON DELETE CASCADE,
    UNIQUE(perfil_id, sistema_id)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(150) NOT NULL,
    email       VARCHAR(150) UNIQUE NOT NULL,
    senha_hash  TEXT NOT NULL,
    perfil_id   INTEGER REFERENCES perfis(id),
    ativo       BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em   TIMESTAMP DEFAULT NOW()
)
""")

# Sistemas padrão
sistemas_seed = [
    ("Central de Sistemas",         "central_sistemas",       "Portal principal com acesso unificado a todas as ferramentas.",           "http://147.15.47.151:8000", "🏠"),
    ("Gerenciador de Credenciais",  "gerenciador_credenciais","Governança e custódia de senhas corporativas com controle de acesso.",    "#",                         "🔐"),
    ("Automação Financeira",        "automacao_financeira",   "Controle de lançamentos, amortizações e auditoria automatizada.",         "#",                         "💰"),
    ("Classificador de E-mails",    "classificador_emails",   "Triagem automática de e-mails por urgência, categoria e filial.",         "#",                         "🤖"),
    ("Conciliação Bancária",        "conciliacao_bancaria",   "Robô RPA que cruza extratos e aponta divergências automaticamente.",      "#",                         "🏦"),
    ("Extração de Documentos",      "extracao_documentos",    "OCR e parsing de PDFs e notas fiscais sem digitação manual.",             "#",                         "📄"),
]

for nome, slug, desc, url, icone in sistemas_seed:
    cur.execute("""
        INSERT INTO sistemas (nome, slug, descricao, url, icone)
        VALUES (%s,%s,%s,%s,%s) ON CONFLICT (slug) DO NOTHING
    """, (nome, slug, desc, url, icone))

# Perfil admin
cur.execute("""
    INSERT INTO perfis (nome, slug, descricao)
    VALUES ('Administrador', 'admin', 'Acesso total ao sistema')
    ON CONFLICT (slug) DO NOTHING
""")
conn.commit()

cur.execute("SELECT id FROM perfis WHERE slug = 'admin'")
admin_perfil_id = cur.fetchone()[0]

# Usuário admin
senha_hash = bcrypt.hashpw(b"REDACTED", bcrypt.gensalt(12)).decode()
cur.execute("""
    INSERT INTO usuarios (nome, email, senha_hash, perfil_id)
    VALUES (%s,%s,%s,%s) ON CONFLICT (email) DO UPDATE SET perfil_id = EXCLUDED.perfil_id
""", ("Almeida Admin", "almeidainteligencia@gmail.com", senha_hash, admin_perfil_id))

conn.commit()
conn.close()
print("Banco inicializado com sucesso.")
print("Admin: almeidainteligencia@gmail.com / REDACTED")
