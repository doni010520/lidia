-- Migration 006: paes_atendimentos_log + triggers + functions

CREATE TABLE IF NOT EXISTS paes_atendimentos_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    telefone TEXT NOT NULL,
    nome TEXT,
    status_momento TEXT,
    ministerio_momento TEXT,
    data_hora TIMESTAMPTZ DEFAULT NOW(),
    tipo_interacao TEXT DEFAULT 'atendimento'
);
CREATE INDEX IF NOT EXISTS idx_atendimentos_telefone ON paes_atendimentos_log(telefone);
CREATE INDEX IF NOT EXISTS idx_atendimentos_data ON paes_atendimentos_log(data_hora DESC);
CREATE INDEX IF NOT EXISTS idx_atendimentos_contact ON paes_atendimentos_log(contact_id);

CREATE OR REPLACE FUNCTION log_novo_contato() RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO paes_atendimentos_log (contact_id, telefone, nome, data_hora, status_momento, tipo_interacao)
    VALUES (NEW.id, NEW.telefone, COALESCE(NEW.full_name, NEW.nome), NEW.created_at, NEW.status, 'primeiro_contato');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_log_novo_contato ON contacts;
CREATE TRIGGER trigger_log_novo_contato AFTER INSERT ON contacts
    FOR EACH ROW EXECUTE FUNCTION log_novo_contato();

CREATE OR REPLACE FUNCTION log_atendimento_automatico() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.ultimo_contato IS DISTINCT FROM OLD.ultimo_contato THEN
        INSERT INTO paes_atendimentos_log (contact_id, telefone, nome, data_hora, status_momento, ministerio_momento)
        VALUES (NEW.id, NEW.telefone, COALESCE(NEW.full_name, NEW.nome), NEW.ultimo_contato, NEW.status, NEW.ministerio_de_interesse);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_log_atendimento ON contacts;
CREATE TRIGGER trigger_log_atendimento AFTER UPDATE ON contacts
    FOR EACH ROW EXECUTE FUNCTION log_atendimento_automatico();

CREATE OR REPLACE FUNCTION match_documents(
    query_embedding vector, match_count integer, filter jsonb DEFAULT '{}'::jsonb
) RETURNS TABLE(id bigint, content text, metadata jsonb, source text, similarity double precision)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT d.id, d.content, d.metadata, d.source,
           1 - (d.embedding <=> query_embedding)::double precision AS similarity
    FROM public.knowledge_chunks d
    WHERE (filter = '{}'::jsonb OR d.metadata @> filter)
      AND (
        (d.metadata->>'data_inicio' IS NULL AND d.metadata->>'data_fim' IS NULL)
        OR (d.metadata->>'data_inicio' IS NOT NULL
            AND CURRENT_DATE >= (d.metadata->>'data_inicio')::date
            AND (d.metadata->>'data_fim' IS NULL OR CURRENT_DATE <= (d.metadata->>'data_fim')::date))
      )
    ORDER BY d.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

CREATE OR REPLACE FUNCTION gerar_cultos_dominicais(meses_a_frente integer)
RETURNS void AS $$
DECLARE
    data_loop DATE;
    data_inicio_geracao DATE := CURRENT_DATE;
    data_fim_geracao DATE := CURRENT_DATE + (meses_a_frente * INTERVAL '1 month');
BEGIN
    FOR data_loop IN SELECT generate_series(data_inicio_geracao, data_fim_geracao, '1 day')::DATE
    LOOP
        IF EXTRACT(DOW FROM data_loop) = 0 THEN
            INSERT INTO eventos_paes (nome, descricao, local, data_inicio, hora, valor, origem, sheets_row_id)
            VALUES ('Culto aos domingos', 'Cultos Regulares, com um tempo de adoracao, onde o Ceu se abre e Deus faz o novo!',
                    'Av. Bernardo Vieira de Melo 1200 | Piedade', data_loop, '08:00', 'Gratuito',
                    'gerador', 'auto:culto-dom:' || data_loop::text || ':08')
            ON CONFLICT (sheets_row_id) DO NOTHING;

            INSERT INTO eventos_paes (nome, descricao, local, data_inicio, hora, valor, origem, sheets_row_id)
            VALUES ('Culto aos domingos', 'Cultos Regulares, com um tempo de adoracao, onde o Ceu se abre e Deus faz o novo!',
                    'Av. Bernardo Vieira de Melo 1200 | Piedade', data_loop, '10:00', 'Gratuito',
                    'gerador', 'auto:culto-dom:' || data_loop::text || ':10')
            ON CONFLICT (sheets_row_id) DO NOTHING;

            INSERT INTO eventos_paes (nome, descricao, local, data_inicio, hora, valor, origem, sheets_row_id)
            VALUES ('Culto aos domingos', 'Cultos Regulares, com um tempo de adoracao, onde o Ceu se abre e Deus faz o novo!',
                    'Av. Bernardo Vieira de Melo 1200 | Piedade', data_loop, '17:00', 'Gratuito',
                    'gerador', 'auto:culto-dom:' || data_loop::text || ':17')
            ON CONFLICT (sheets_row_id) DO NOTHING;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

ALTER TABLE eventos_paes DROP CONSTRAINT IF EXISTS ck_eventos_origem;
ALTER TABLE eventos_paes ADD CONSTRAINT ck_eventos_origem
    CHECK (origem IN ('sheets', 'painel', 'gerador'));
