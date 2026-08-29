"""Carimbo de data no histórico (stamp_past_messages).

Contexto (bug 28/08/2026): o histórico chega ao modelo sem nenhuma marca de
tempo. Uma negativa da Diacon de 3 dias atrás ("Não temos GAS de 23/08") fica
no contexto parecendo fato de agora — e o modelo repete a resposta em vez de
consultar a Diacon de novo. O material já tinha sido publicado nesse meio-tempo.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.conversation_service import stamp_past_messages

SP = ZoneInfo("America/Sao_Paulo")
HOJE = datetime(2026, 8, 28, 19, 32, tzinfo=SP)


class TestCarimboDeData:
    def test_mensagem_de_dia_anterior_recebe_carimbo(self):
        entries = [{
            "role": "assistant",
            "content": "Camila, não temos o GAS para o domingo, 23/08/2026.",
            "_created_at": datetime(2026, 8, 25, 8, 14, tzinfo=SP),
        }]
        out = stamp_past_messages(entries, now=HOJE)
        assert out[0]["content"].startswith("[25/08]")
        assert "não temos o GAS" in out[0]["content"]

    def test_mensagem_de_hoje_nao_recebe_carimbo(self):
        entries = [{
            "role": "user",
            "content": "Gostaria do gas de domingo",
            "_created_at": datetime(2026, 8, 28, 19, 30, tzinfo=SP),
        }]
        out = stamp_past_messages(entries, now=HOJE)
        assert out[0]["content"] == "Gostaria do gas de domingo"

    def test_resultado_de_tool_vencido_fica_datado(self):
        """O caso real: a linha que o modelo copiou palavra por palavra."""
        entries = [{
            "role": "tool",
            "tool_call_id": "call_dx8vjps1",
            "content": "Não temos GAS de 23/08/2026. A mais recente é a de 09/08/2026.",
            "_created_at": datetime(2026, 8, 25, 8, 14, tzinfo=SP),
        }]
        out = stamp_past_messages(entries, now=HOJE)
        assert out[0]["content"].startswith("[25/08]")
        assert out[0]["tool_call_id"] == "call_dx8vjps1"

    def test_chave_privada_nunca_vaza_para_a_openai(self):
        """_created_at é uso interno: a OpenAI rejeita chave desconhecida."""
        entries = [
            {"role": "user", "content": "oi", "_created_at": datetime(2026, 8, 25, 8, 0, tzinfo=SP)},
            {"role": "assistant", "content": "Olá!", "_created_at": HOJE},
        ]
        out = stamp_past_messages(entries, now=HOJE)
        assert all("_created_at" not in e for e in out)

    def test_assistant_com_tool_calls_e_sem_texto_nao_quebra(self):
        entries = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_x", "type": "function",
                            "function": {"name": "buscar_material", "arguments": "{}"}}],
            "_created_at": datetime(2026, 8, 25, 8, 14, tzinfo=SP),
        }]
        out = stamp_past_messages(entries, now=HOJE)
        assert out[0]["content"] == ""
        assert out[0]["tool_calls"][0]["id"] == "call_x"

    def test_entrada_sem_created_at_passa_intacta(self):
        entries = [{"role": "user", "content": "mensagem atual"}]
        out = stamp_past_messages(entries, now=HOJE)
        assert out[0]["content"] == "mensagem atual"

    def test_nao_carimba_duas_vezes(self):
        entries = [{
            "role": "assistant",
            "content": "[25/08] Não temos o GAS.",
            "_created_at": datetime(2026, 8, 25, 8, 14, tzinfo=SP),
        }]
        out = stamp_past_messages(entries, now=HOJE)
        assert out[0]["content"].count("[25/08]") == 1

    def test_ano_diferente_mostra_o_ano(self):
        entries = [{
            "role": "user",
            "content": "Gostaria do GAS de 06/06",
            "_created_at": datetime(2025, 6, 6, 10, 0, tzinfo=SP),
        }]
        out = stamp_past_messages(entries, now=HOJE)
        assert out[0]["content"].startswith("[06/06/2025]")

    def test_created_at_em_utc_usa_o_dia_de_sao_paulo(self):
        """22:32 UTC do dia 28 é ainda dia 28 em SP (19:32) — não pode virar 29."""
        entries = [{
            "role": "user",
            "content": "Gostaria do gas de domingo",
            "_created_at": datetime(2026, 8, 28, 22, 32, tzinfo=ZoneInfo("UTC")),
        }]
        out = stamp_past_messages(entries, now=HOJE)
        assert out[0]["content"] == "Gostaria do gas de domingo"
