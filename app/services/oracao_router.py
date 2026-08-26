"""Pré-roteador determinístico de oração.

Motivo de existir
-----------------
A intenção "quero o link do mural / oração do dia" é crítica e frequente, e
estava sendo decidida pelo LLM. Dois efeitos ruins apareciam em produção:

1. O `dica_rag` (busca vetorial) recupera o chunk da Alvorada porque ele é
   semanticamente próximo de qualquer frase com "oração" + "link". O modelo
   lia um texto pronto e plausível no topo do prompt e respondia com ele em
   vez de chamar `oracao_do_dia`. Resultado: link errado, no primeiro turno.

2. O "portão" de desambiguação do prompt fazia uma pergunta extra mesmo
   quando a pessoa já tinha sido específica ("link de oração do mural").
   Turno extra = desistência.

A solução segue o mesmo princípio já usado nos outros agentes: intenção
crítica é resolvida em código, antes do LLM. Aqui a gente:

- detecta a intenção por regra determinística;
- executa a ferramenta direto (mural) ou injeta os dados autoritativos
  (alvorada);
- SUPRIME o `dica_rag` naquele turno, matando o viés do RAG na raiz sem
  mexer no RAG dos demais fluxos.

O LLM continua no comando da resposta — mas recebe o fato já resolvido.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


# ──────────────────────────────────────────────────────────────────────
# Normalização
# ──────────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """Minúsculas, sem acento, espaços colapsados."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().split())


# ──────────────────────────────────────────────────────────────────────
# Vocabulários de intenção
# ──────────────────────────────────────────────────────────────────────

# Pedido PESSOAL de oração → NÃO é território deste roteador.
# Deixamos passar para o LLM, que chama `pedido_oracao`.
_PESSOAL = (
    "orem por mim",
    "ore por mim",
    "ora por mim",
    "orar por mim",
    "preciso de oracao",
    "preciso de uma oracao",
    "pedido de oracao",
    "pedir oracao",
    "peco oracao",
    "intercess",
    "orem pela",
    "orem pelo",
    "ore pela",
    "ore pelo",
    "oracao pela minha",
    "oracao pelo meu",
    "esta doente",
    "estou passando por",
)

# Encontros semanais ao vivo (vídeo).
_ALVORADA = (
    "alvorada",
)

# Mural / calendário de oração corporativo do dia.
_MURAL = (
    "mural",
    "oracao do dia",
    "oracao de hoje",
    "calendario de oracao",
    "calendario da oracao",
    "motivo de oracao",
    "motivo da oracao",
    "tema de oracao",
    "tema da oracao",
    "tema de hoje",
    "orar com a igreja",
    "orar junto com a igreja",
    "orar junto",
    "orar em unidade",
    "card de oracao",
    "card da oracao",
    "link de oracao",
    "link da oracao",
    "link de oracao do dia",
    "link para orar",
    "registrar oracao",
    "registrar minha oracao",
    "participar da oracao",
    "como faco pra orar",
    "como participo da oracao",
    "manda a oracao",
    "me manda a oracao",
    "quero a oracao",
    "quero orar",
)


# ──────────────────────────────────────────────────────────────────────
# Alvoradas — fonte única de verdade
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Alvorada:
    nome: str
    quando: str
    link: str


def alvoradas() -> list[Alvorada]:
    """Lê as Alvoradas do settings.

    Ficam aqui (e não em `knowledge_chunks`) de propósito: link é dado
    volátil e precisa de um lugar revisável. Dentro de embedding ninguém
    revisa e o RAG entrega com confiança total, errado ou não.
    """
    brutas = [
        Alvorada(
            "Alvorada de Oração",
            settings.alvorada_oracao_quando,
            settings.alvorada_oracao_link,
        ),
        Alvorada(
            "Alvorada Feminina",
            settings.alvorada_feminina_quando,
            settings.alvorada_feminina_link,
        ),
        Alvorada(
            "Alvorada Homens de Valor",
            settings.alvorada_homens_quando,
            settings.alvorada_homens_link,
        ),
    ]
    return [a for a in brutas if a.link]


def alvoradas_texto(*, compacto: bool = False) -> str:
    """Bloco de texto pronto com as Alvoradas configuradas."""
    itens = alvoradas()
    if not itens:
        return ""
    if compacto:
        linhas = [f"• {a.nome} — {a.quando}: {a.link}" for a in itens]
        return "\n".join(linhas)
    linhas = [f"🕕 *{a.nome}* — {a.quando}\n{a.link}" for a in itens]
    return "\n\n".join(linhas)


# ──────────────────────────────────────────────────────────────────────
# Resultado
# ──────────────────────────────────────────────────────────────────────

@dataclass
class OracaoRoute:
    """Resultado do pré-roteamento.

    handled      → o roteador assumiu o turno (RAG deve ser suprimido)
    system_note  → bloco autoritativo anexado ao final do system prompt
    tools_called → nomes de tools executadas em código (para analytics)
    """
    handled: bool = False
    system_note: str = ""
    tools_called: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# Detecção
# ──────────────────────────────────────────────────────────────────────

def detect(user_text: str) -> str | None:
    """Retorna 'mural', 'alvorada' ou None.

    Ordem importa:
    1. Pedido pessoal sai fora (é `pedido_oracao`, outro fluxo).
    2. "alvorada" citada explicitamente ganha.
    3. Qualquer sinal de oração corporativa → mural.
    """
    t = _norm(user_text)
    if not t:
        return None

    # Mensagens de sistema (mídia, localização) não roteiam oração.
    if t.startswith("[sistema]") or t.startswith("[localizacao]"):
        return None

    if any(p in t for p in _PESSOAL):
        return None

    if any(p in t for p in _ALVORADA):
        return "alvorada"

    if any(p in t for p in _MURAL):
        return "mural"

    return None


# ──────────────────────────────────────────────────────────────────────
# Resolução
# ──────────────────────────────────────────────────────────────────────

async def resolve(
    user_text: str,
    phone: str,
    db: AsyncSession,
) -> OracaoRoute:
    """Executa o pré-roteamento. Chamado pelo pipeline antes do LLM."""
    if not settings.oracao_router_enabled:
        return OracaoRoute()

    intent = detect(user_text)
    if intent is None:
        return OracaoRoute()

    log = logger.bind(phone=phone)

    # ── Alvorada: entrega os dados autoritativos, sem RAG ──
    if intent == "alvorada":
        bloco = alvoradas_texto()
        if not bloco:
            log.warning("oracao_router: alvorada pedida mas nenhum link configurado")
            return OracaoRoute()

        log.info("oracao_router: intenção=alvorada (RAG suprimido)")
        return OracaoRoute(
            handled=True,
            system_note=(
                "## ⛳ FATO JÁ RESOLVIDO NESTE TURNO — ALVORADAS\n\n"
                "A pessoa pediu uma das Alvoradas (encontros semanais ao vivo "
                "por vídeo). Os dados abaixo são a ÚNICA fonte válida — "
                "entregue exatamente estes links e horários, sem alterar, sem "
                "completar e sem buscar em outro lugar:\n\n"
                f"{bloco}\n\n"
                "Se ela não disse qual das Alvoradas quer, liste as disponíveis "
                "acima em uma mensagem curta. Feche oferecendo, em uma linha, o "
                "mural da oração do dia caso ela também queira orar com a igreja."
            ),
        )

    # ── Mural: executa a ferramenta AGORA, em código ──
    from app.tools.tool_modules import oracao_do_dia

    log.info("oracao_router: intenção=mural → executando oracao_do_dia (RAG suprimido)")
    try:
        resultado = await oracao_do_dia.execute({"telefone": phone}, phone, db)
    except Exception:
        log.exception("oracao_router: falha ao executar oracao_do_dia")
        return OracaoRoute(
            handled=True,
            system_note=(
                "## ⛳ FATO JÁ RESOLVIDO NESTE TURNO — MURAL DE ORAÇÃO\n\n"
                "Houve uma falha técnica ao gerar o link do mural. Diga em uma "
                "frase curta e acolhedora que teve um problema para enviar o "
                "link agora e que ela pode pedir de novo em instantes. Não "
                "invente link nenhum."
            ),
            tools_called=["oracao_do_dia"],
        )

    return OracaoRoute(
        handled=True,
        system_note=(
            "## ⛳ FATO JÁ RESOLVIDO NESTE TURNO — MURAL DE ORAÇÃO\n\n"
            "O mural da oração do dia JÁ FOI ENVIADO para a pessoa por outra "
            "mensagem, junto com os horários e links das Alvoradas. Retorno da "
            f"operação: {resultado}\n\n"
            "Sua resposta agora é APENAS uma frase curta e acolhedora "
            "confirmando o envio — algo como \"Mandei aqui pra você 🙏\". "
            "Chame `oracao_do_dia` de novo somente se o retorno acima indicar "
            "falha. Não repita o link, não descreva o conteúdo, não faça "
            "perguntas de escolha e não ofereça a Alvorada: ela já foi junto."
        ),
        tools_called=["oracao_do_dia"],
    )
