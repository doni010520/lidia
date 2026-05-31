"""Popular tabela equipes_responsaveis com as 17 equipes da PAES.

Uso:
    python -m scripts.seed_equipes
    # ou via docker exec:
    docker compose exec app python -m scripts.seed_equipes
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db import engine

SEED_SQL = """
INSERT INTO equipes_responsaveis (equipe, telefones_responsaveis, emails, sheets_log_url) VALUES
('Oração',
   ARRAY['5581999861921','558137717049'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/1C16ijmcVaeXSIKioDuyFFvUzC52Vo7UZnqRdqUWv79s'),

('Células',
   ARRAY['5581998390927'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/1lOZZYcysW_8kcQvW4dvK2BxEfWGf8nU8ohDULcL5F88'),

('Louvor',
   ARRAY['5581998390927'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/18xhTG_wEWedmBnLhicClHL4UKpqnYVtQe3wIL5ppLno'),

('Cursilho Masculino',
   ARRAY['5581991018253'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/1qFfvDih8Z1Hcs72G-17bCi4AuD09FezQtwBJhn6va00'),

('Cursilho Feminino',
   ARRAY['5581991015612'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/1v-Pc7l58eBvnygewzK2rcHVMk3AvzGiY-e2ZcifJJ04'),

('Batismo',
   ARRAY['5581996920063'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/1ujcwdbatZO72-IWS-XlRZZrJA8_6KU7zjPVT_5_qDPk'),

('Apresentação de crianças',
   ARRAY['5581996920063'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/1ujcwdbatZO72-IWS-XlRZZrJA8_6KU7zjPVT_5_qDPk'),

('Gabinete Pastoral',
   ARRAY['5581996920063'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/1TvaotwAlaZ33MEpfe8sbQgPgiAS0pJJr89X45TujYzk'),

('Casa da Esperança',
   ARRAY['5581996920063'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/1zajWv3fKlCQC9tL17pI2S6V_Z-S463gpWv1IjqqaKwc'),

('Dízimos e Ofertas',
   ARRAY['5581996920063'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/13ClATq2pQ7rfQtjht8h8-E5p2_qMrNL76tR4Y_V-DQk'),

('Agenda de Eventos',
   ARRAY['5581996174710'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/114HWg1TCknNk4wmeLTEWIA4sN5dRk72QyAiQexOcDqE'),

('Decisão',
   ARRAY['558193163985'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/1-LhS0bUdim7uMm8QOUIqQCMSFgvPoaCYrnHAnItehD0'),

('Visita guiada',
   ARRAY['5581996920063'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/1W15tt7QjqMpa3g8NUfgnmJtfpk-tG2h1RZJmcDZnALM'),

('Dúvidas Gerais',
   ARRAY['5581996920063'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/1R7W8hu8CV0PeC-mCgOo4M4bUW85FQvqucuj7DETJn6Y'),

('Ministérios',
   ARRAY['5581996920063'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/1R7W8hu8CV0PeC-mCgOo4M4bUW85FQvqucuj7DETJn6Y'),

('Fluir',
   ARRAY['5581998865077'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/1roqsvH9CVnzd2R4JEcZMADk5Zu2nP2LtitcjOSCc6Yo'),

('Casais',
   ARRAY['558191442252'],
   ARRAY['paescatedral@gmail.com'],
   'https://docs.google.com/spreadsheets/d/1HqlLAaYAwJI93GeyFcA9Yds9cOLy31kWPH1pTV5bMa0')

ON CONFLICT (equipe) DO UPDATE SET
    telefones_responsaveis = EXCLUDED.telefones_responsaveis,
    emails = EXCLUDED.emails,
    sheets_log_url = EXCLUDED.sheets_log_url;
"""


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text(SEED_SQL))
    print(f"✅ 17 equipes inseridas/atualizadas com sucesso.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
