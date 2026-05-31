ALTER TABLE eventos_paes
    ADD COLUMN IF NOT EXISTS origem VARCHAR(20) DEFAULT 'painel'
        CHECK (origem IN ('sheets', 'painel'));

-- Marca registros existentes como vindos do sheets
UPDATE eventos_paes
SET origem = 'sheets'
WHERE sheets_row_id IS NOT NULL AND sheets_row_id NOT LIKE 'painel:%';
