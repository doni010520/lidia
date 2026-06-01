-- Migration 009: eventos_paes.hora vira TEXT
--
-- Motivação: a planilha PAES de eventos tem horários em formato livre
-- ("18hrs", "manhã", "10h às 12h", etc). TIME era restritivo demais.

ALTER TABLE eventos_paes
    ALTER COLUMN hora TYPE TEXT
    USING (CASE WHEN hora IS NULL THEN NULL ELSE hora::TEXT END);
