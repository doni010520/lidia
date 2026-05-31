CREATE EXTENSION IF NOT EXISTS vector;

-- ─── Contatos ───
CREATE TABLE contacts (
    id SERIAL PRIMARY KEY,
    telefone TEXT UNIQUE NOT NULL,
    nome TEXT,
    full_name TEXT,
    email TEXT,
    status TEXT,
    aniversario DATE,
    ultimo_contato TIMESTAMPTZ,
    ai_enabled BOOLEAN DEFAULT TRUE,
    cadastro_completo BOOLEAN DEFAULT FALSE,
    metadata_json JSONB DEFAULT '{}'::jsonb,
    is_blocked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_contacts_telefone ON contacts(telefone);

-- ─── Mensagens (memória de chat) ───
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    phone TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_call_id TEXT,
    tool_name TEXT,
    tool_calls_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_phone_created ON messages(phone, created_at DESC);

-- ─── Base de conhecimento (RAG) ───
CREATE TABLE knowledge_chunks (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(1536),
    metadata JSONB DEFAULT '{}'::jsonb,
    source TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_knowledge_embedding ON knowledge_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ─── Eventos da PAES ───
CREATE TABLE eventos_paes (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    descricao TEXT,
    local TEXT,
    data_inicio DATE,
    data_final DATE,
    hora TIME,
    valor TEXT,
    link TEXT,
    media TEXT,
    sheets_row_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_eventos_data ON eventos_paes(data_inicio, data_final);

-- ─── Plano de leitura bíblica ───
CREATE TABLE plano_de_leitura (
    id SERIAL PRIMARY KEY,
    data DATE UNIQUE,
    leitura TEXT,
    capitulos TEXT,
    semana INT,
    livro TEXT,
    sheets_row_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_plano_data ON plano_de_leitura(data);

-- ─── Novos convertidos ───
CREATE TABLE novos_convertidos (
    id SERIAL PRIMARY KEY,
    telefone TEXT UNIQUE NOT NULL,
    nome TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Analytics ───
CREATE TABLE llm_analytics (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    model_name TEXT,
    agent_type TEXT,
    prompt_tokens INT,
    completion_tokens INT,
    total_tokens INT,
    cost_usd NUMERIC(10,6),
    intent_detected TEXT,
    sentiment_score NUMERIC(3,2),
    response_time_ms INT,
    tools_called TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_analytics_session_created ON llm_analytics(session_id, created_at DESC);

-- ─── Equipes para notificação ───
CREATE TABLE equipes_responsaveis (
    id SERIAL PRIMARY KEY,
    equipe TEXT UNIQUE NOT NULL,
    descricao TEXT,
    telefones_responsaveis TEXT[],
    emails TEXT[],
    sheets_log_url TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

-- ─── Triggers ───
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER contacts_updated_at BEFORE UPDATE ON contacts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER eventos_updated_at BEFORE UPDATE ON eventos_paes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
