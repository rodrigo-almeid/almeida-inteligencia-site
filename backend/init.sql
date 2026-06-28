CREATE TABLE IF NOT EXISTS usuarios (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(150) NOT NULL,
    email       VARCHAR(150) UNIQUE NOT NULL,
    senha_hash  TEXT NOT NULL,
    perfil      VARCHAR(50) NOT NULL DEFAULT 'cliente',
    perfil_id   INTEGER,
    ativo       BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em   TIMESTAMP DEFAULT NOW()
);
