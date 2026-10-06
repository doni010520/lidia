-- Disparo só de texto (tipo 'texto') e áudio como mensagem de voz (arquivo_tipo 'ptt').
-- Idempotente: o entrypoint reaplica todas as migrations a cada boot.

-- O 003 criou o CHECK inline (nome automático); o model usa ck_disparo_arquivo_tipo.
ALTER TABLE disparos DROP CONSTRAINT IF EXISTS disparos_arquivo_tipo_check;
ALTER TABLE disparos DROP CONSTRAINT IF EXISTS ck_disparo_arquivo_tipo;
ALTER TABLE disparos ADD CONSTRAINT ck_disparo_arquivo_tipo
    CHECK (arquivo_tipo IS NULL OR arquivo_tipo IN ('image', 'document', 'video', 'ptt'));

-- Roda depois do 012, que recria ck_disparo_tipo só com ('midia', 'contato').
ALTER TABLE disparos DROP CONSTRAINT IF EXISTS ck_disparo_tipo;
ALTER TABLE disparos ADD CONSTRAINT ck_disparo_tipo
    CHECK (tipo IN ('midia', 'contato', 'texto'));
