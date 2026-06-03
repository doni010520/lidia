-- Migration 012: telefone do responsável de Louvor (Victor, do workflow n8n original)
UPDATE equipes_responsaveis
SET telefones_responsaveis = ARRAY['5581998390927']
WHERE equipe = 'Louvor' AND (telefones_responsaveis IS NULL OR array_length(telefones_responsaveis,1) IS NULL);
