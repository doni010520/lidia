"""Helper compartilhado: resolve o telefone confiável para chamadas Diacon.

Regra de segurança (guia Diacon, 22/10/26): o telefone vem SEMPRE do
remetente que o webhook entrega. Nunca de um número digitado no texto, nem do
campo 'telefone' que o modelo preenche: várias chamadas decidem pelo telefone
o que a pessoa pode ver (relatório de células, panorama de admin, materiais,
agenda interna), e um número digitado deixaria qualquer um se passar por
outra pessoa.

Antes o argumento do modelo vencia quando tinha >=10 dígitos — "me manda o
relatório do 81 99788-4531" entregava o relatório do dono desse número.
"""
from __future__ import annotations


def resolve_phone(raw: object, fallback: str) -> str:
    """Retorna o telefone do remetente (webhook).

    Args:
        raw: o que o modelo colocou no campo 'telefone'. Ignorado quando há
            remetente; só é usado quando não existe nenhum (ex.: chamada
            interna sem conversa), e mesmo assim só se parecer um telefone.
        fallback: telefone real do remetente, vindo do webhook.
    """
    if fallback:
        return fallback
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    return digits if len(digits) >= 10 else ""
