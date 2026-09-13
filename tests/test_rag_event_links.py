"""A Dica de resposta não carrega link de evento.

A planilha de informações é escrita à mão e envelhece: em 13/09 ela ainda
dizia "inscrições abertas" da Conferência 30 Anos (encerrada em 22/08), e o
modelo copiou o link. Link de evento é da Diacon, via buscar_evento.
"""
from __future__ import annotations

from app.services.rag_service import RAGChunk, RAGService


def test_dica_nao_traz_link_de_evento_mas_mantem_o_assunto():
    svc = RAGService.__new__(RAGService)
    chunk = RAGChunk(
        content=(
            "Pergunta: Preciso me inscrever para ir à conferência?\n"
            "Resposta: As inscrições para a Conferência PAES 30 Anos | LEGADO estão abertas e são "
            "feitas pelo site: https://diacon.ia.br/e/conf-30-anos-paes-08-20\n"
            "Se precisar de ajuda, fale com a Secretaria: https://wa.me/558196920063"
        ),
        source="sheets_informacoes", score=0.686,
    )

    result = svc.format_chunks([chunk])

    assert "diacon.ia.br/e/" not in result
    assert "Conferência PAES 30 Anos" in result
    assert "https://wa.me/558196920063" in result
