"""Helper compartilhado: resolve o telefone confiável para chamadas Diacon.

O modelo às vezes preenche o campo 'telefone' com placeholder
('(não informado)', 'não informado', vazio) quando a pessoa não digita o
número — como é string não-vazia, um `args.get("telefone") or phone` ingênuo
usaria o lixo e a Diacon devolvia bad_request/forbidden. Este helper limpa
para dígitos e só usa o argumento se ele parecer um telefone de verdade;
caso contrário cai no número real do remetente (webhook).
"""
from __future__ import annotations


def resolve_phone(raw: object, fallback: str) -> str:
    """Retorna um telefone confiável a partir do arg do modelo + o do webhook.

    Args:
        raw: o que o modelo colocou no campo 'telefone' (pode ser lixo).
        fallback: telefone real do remetente, vindo do webhook.

    Returns:
        O arg (só dígitos) se tiver >=10 dígitos; senão o fallback.
    """
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    return digits if len(digits) >= 10 else (fallback or "")
