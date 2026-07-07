-- Migration 010: corrige match_documents - id deve ser integer (não bigint)
--
-- knowledge_chunks.id é INTEGER (não BIGINT), causando
-- DatatypeMismatchError quando a função tenta retornar.
-- Postgres não permite alterar RETURNS TABLE via CREATE OR REPLACE,
-- então precisa DROP antes.

DROP FUNCTION IF EXISTS match_documents(vector, integer, jsonb);

CREATE OR REPLACE FUNCTION match_documents(
    query_embedding vector, match_count integer, filter jsonb DEFAULT '{}'::jsonb
) RETURNS TABLE(id integer, content text, metadata jsonb, source text, similarity double precision)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT d.id, d.content, d.metadata, d.source,
           1 - (d.embedding <=> query_embedding)::double precision AS similarity
    FROM knowledge_chunks d
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
