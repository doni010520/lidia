-- Módulo de Disparos em Massa + Auth do Painel
-- Dependências: contacts (001), uq_eventos_sheets_row (002)

CREATE TABLE disparos (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    arquivo_url TEXT NOT NULL,
    arquivo_tipo VARCHAR(20) NOT NULL
        CHECK (arquivo_tipo IN ('image', 'document', 'video')),
    arquivo_nome VARCHAR(255),
    legenda TEXT,
    status VARCHAR(20) DEFAULT 'agendado'
        CHECK (status IN ('agendado', 'enviando', 'concluido', 'falhou', 'cancelado')),
    agendado_para TIMESTAMPTZ,
    total INTEGER DEFAULT 0,
    enviados INTEGER DEFAULT 0,
    falhas INTEGER DEFAULT 0,
    filtro_status TEXT,
    filtro_telefones TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100)
);

CREATE INDEX idx_disparos_status ON disparos(status);
CREATE INDEX idx_disparos_agendado ON disparos(agendado_para)
    WHERE status = 'agendado';

CREATE TABLE disparo_log (
    id SERIAL PRIMARY KEY,
    disparo_id UUID REFERENCES disparos(id) ON DELETE CASCADE,
    telefone VARCHAR(20) NOT NULL,
    nome VARCHAR(255),
    status VARCHAR(20) DEFAULT 'enviado'
        CHECK (status IN ('enviado', 'falhou', 'pulado')),
    enviado_em TIMESTAMPTZ DEFAULT NOW(),
    erro TEXT
);

CREATE INDEX idx_disparo_log_disparo ON disparo_log(disparo_id);
CREATE UNIQUE INDEX uq_disparo_log_pair ON disparo_log(disparo_id, telefone);

CREATE TABLE usuarios_painel (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    senha_hash VARCHAR(255) NOT NULL,
    nome VARCHAR(100),
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
