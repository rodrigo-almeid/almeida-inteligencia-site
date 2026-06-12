CREATE TABLE IF NOT EXISTS usuarios (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(150) NOT NULL,
    email       VARCHAR(150) UNIQUE NOT NULL,
    senha_hash  TEXT NOT NULL,
    perfil      VARCHAR(50) NOT NULL DEFAULT 'cliente',
    ativo       BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em   TIMESTAMP DEFAULT NOW()
);

-- Usuário admin inicial
INSERT INTO usuarios (nome, email, senha_hash, perfil)
VALUES (
    'Almeida Admin',
    'almeidainteligencia@gmail.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBpj2BpRJMzKnm',
    'admin'
)
ON CONFLICT (email) DO NOTHING;
