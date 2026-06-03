-- Migration 011: popula equipes_responsaveis com 15 equipes do n8n
--
-- Cada equipe tem uma planilha onde recebe notificações da LidIA.
-- Telefones e emails podem ser preenchidos depois via painel admin.

INSERT INTO equipes_responsaveis (equipe, sheets_log_url, is_active) VALUES
  ('Células',            '1lOZZYcysW_8kcQvW4dvK2BxEfWGf8nU8ohDULcL5F88', true),
  ('Louvor',             '18xhTG_wEWedmBnLhicClHL4UKpqnYVtQe3wIL5ppLno', true),
  ('Fluir',              '1roqsvH9CVnzd2R4JEcZMADk5Zu2nP2LtitcjOSCc6Yo', true),
  ('Casais',             '1HqlLAaYAwJI93GeyFcA9Yds9cOLy31kWPH1pTV5bMa0', true),
  ('Cursilho Masculino', '1qFfvDih8Z1Hcs72G-17bCi4AuD09FezQtwBJhn6va00', true),
  ('Cursilho Feminino',  '1v-Pc7l58eBvnygewzK2rcHVMk3AvzGiY-e2ZcifJJ04', true),
  ('Oração',             '1C16ijmcVaeXSIKioDuyFFvUzC52Vo7UZnqRdqUWv79s', true),
  ('Batismo',            '1ujcwdbatZO72-IWS-XlRZZrJA8_6KU7zjPVT_5_qDPk', true),
  ('Gabinete Pastoral',  '1TvaotwAlaZ33MEpfe8sbQgPgiAS0pJJr89X45TujYzk', true),
  ('Casa da Esperança',  '1zajWv3fKlCQC9tL17pI2S6V_Z-S463gpWv1IjqqaKwc', true),
  ('Dízimos e Ofertas',  '13ClATq2pQ7rfQtjht8h8-E5p2_qMrNL76tR4Y_V-DQk', true),
  ('Agenda de Eventos',  '114HWg1TCknNk4wmeLTEWIA4sN5dRk72QyAiQexOcDqE', true),
  ('Decisão',            '1-LhS0bUdim7uMm8QOUIqQCMSFgvPoaCYrnHAnItehD0', true),
  ('Visita guiada',      '1W15tt7QjqMpa3g8NUfgnmJtfpk-tG2h1RZJmcDZnALM', true),
  ('Dúvidas Gerais',     '1R7W8hu8CV0PeC-mCgOo4M4bUW85FQvqucuj7DETJn6Y', true),
  ('Apresentação de crianças', NULL, true),
  ('Ministérios',        NULL, true),
  ('Plano de Leitura',   NULL, true),
  ('Comunicação',        NULL, true)
ON CONFLICT (equipe) DO UPDATE SET
  sheets_log_url = EXCLUDED.sheets_log_url,
  is_active = EXCLUDED.is_active;
