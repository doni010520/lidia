-- Migration 008
ALTER TABLE contacts
    ADD COLUMN IF NOT EXISTS pediu_aniversario TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS follow_up TEXT,
    ADD COLUMN IF NOT EXISTS etiqueta TEXT,
    ADD COLUMN IF NOT EXISTS ministerio_de_interesse TEXT,
    ADD COLUMN IF NOT EXISTS ministerio_de_servico TEXT;
