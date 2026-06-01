-- Migration 007
CREATE TABLE IF NOT EXISTS pastores_aniversario (
    id BIGSERIAL PRIMARY KEY,
    nome TEXT,
    telefone TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pastores_telefone ON pastores_aniversario(telefone);

CREATE TABLE IF NOT EXISTS liderancas (
    id BIGSERIAL PRIMARY KEY,
    nome TEXT,
    telefone TEXT,
    ministerio TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_liderancas_telefone ON liderancas(telefone);
