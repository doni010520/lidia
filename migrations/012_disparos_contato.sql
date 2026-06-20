-- Disparo com contato (vCard): novo tipo 'contato' além de 'midia'
-- Idempotente.

ALTER TABLE disparos ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'midia';
ALTER TABLE disparos ADD COLUMN IF NOT EXISTS contato_nome TEXT;
ALTER TABLE disparos ADD COLUMN IF NOT EXISTS contato_telefone TEXT;
ALTER TABLE disparos ADD COLUMN IF NOT EXISTS contato_organizacao TEXT;

-- Para o tipo 'contato' não há arquivo
ALTER TABLE disparos ALTER COLUMN arquivo_url DROP NOT NULL;
ALTER TABLE disparos ALTER COLUMN arquivo_tipo DROP NOT NULL;

-- Restringe os valores de tipo
ALTER TABLE disparos DROP CONSTRAINT IF EXISTS ck_disparo_tipo;
ALTER TABLE disparos ADD CONSTRAINT ck_disparo_tipo CHECK (tipo IN ('midia', 'contato'));
