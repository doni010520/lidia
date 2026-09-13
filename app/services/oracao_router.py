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

import json
import unicodedata
import uuid
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
    # "oração diária" é como boa parte das pessoas chama o mural. Sem estas
    # duas entradas a frase sozinha ("oração diária") escapava do roteador e
    # caía no LLM, que a tratava como coisa que não tem e encaminhava.
    "oracao diaria",
    "calendario diario",
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

    handled        → o roteador assumiu o turno (RAG deve ser suprimido)
    system_note    → bloco autoritativo anexado ao final do system prompt
    tools_called   → nomes de tools executadas em código (para analytics)
    suppress_tools → tools a REMOVER da lista oferecida ao LLM neste turno
    transcript     → o que foi executado em código, no formato de mensagem
                     da OpenAI (par assistant+tool), para entrar no histórico
    """
    handled: bool = False
    system_note: str = ""
    tools_called: list[str] = field(default_factory=list)
    suppress_tools: list[str] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# Transcrição
# ──────────────────────────────────────────────────────────────────────

def _transcrever(tool_name: str, arguments: dict, resultado: str) -> list[dict]:
    """Descreve uma execução feita em código como o loop de tools a descreveria.

    Sem isso o roteador agia sem deixar rastro: o envio acontecia fora do
    loop de tools e nada era gravado em `lidia.messages`. No dia seguinte a
    LidIA lia o próprio histórico, via o pedido da pessoa e a sua resposta, e
    nenhuma linha dizendo que o mural tinha saído — então tratava o pedido
    como não atendido e "encaminhava novamente".

    Devolver o par no formato da OpenAI faz um turno resolvido em código
    ficar indistinguível de um turno resolvido pelo LLM, tanto para o modelo
    quanto para quem for auditar a conversa depois.
    """
    call_id = f"call_router_{uuid.uuid4().hex[:16]}"
    return [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(arguments, ensure_ascii=False),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": call_id,
            "name": tool_name,
            "content": resultado,
        },
    ]


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
        ok, resultado = await oracao_do_dia.enviar(phone)
    except Exception:
        log.exception("oracao_router: falha inesperada ao executar oracao_do_dia")
        ok, resultado = False, "erro inesperado ao gerar o link."

    transcript = _transcrever("oracao_do_dia", {"telefone": phone}, resultado)

    # ── Falha: NADA chegou na pessoa ──
    # A tool fica FORA de suppress_tools de propósito: o LLM precisa poder
    # tentar de novo. E o note não pode afirmar que enviou.
    if not ok:
        log.warning(f"oracao_router: envio do mural não concluído — {resultado}")
        return OracaoRoute(
            handled=True,
            system_note=(
                "## ⛳ SITUAÇÃO APURADA NESTE TURNO — MURAL DE ORAÇÃO\n\n"
                "A tentativa de enviar o mural da oração do dia NÃO se concluiu: "
                f"a pessoa NÃO recebeu nada. Motivo técnico: {resultado}\n\n"
                "NÃO diga que enviou e NÃO invente link nenhum. Explique em uma "
                "frase curta e acolhedora, sem jargão técnico, o que houve e qual "
                "o próximo passo. Se o motivo for cadastro, ofereça ajudar a "
                "resolver isso agora. Se for falha temporária, você pode chamar "
                "`oracao_do_dia` uma única vez para tentar novamente."
            ),
            tools_called=["oracao_do_dia"],
            transcript=transcript,
        )

    # ── Sucesso ──
    # `suppress_tools` tira as tools da lista deste turno. Aviso no prompt é
    # pedido; tirar da lista é garantia. Saem duas, por motivos diferentes —
    # os dois observados em produção:
    #
    # `oracao_do_dia`: sem isso o modelo chamava de novo mesmo com o aviso
    #   escrito no prompt, e a pessoa recebia o mural DUPLICADO, com dois
    #   links autenticados distintos.
    #
    # `notificar_time_interno`: é o efeito colateral de tirar `oracao_do_dia`
    #   da lista. O modelo procura a ferramenta do mural, não acha, e cai na
    #   regra genérica do prompt ("não consegui atender → encaminhe para a
    #   equipe"). Em 09/09 a pessoa recebeu o card com o link e leu, no mesmo
    #   turno, "já encaminhei sua solicitação para a equipe de oração para que
    #   enviem o link do calendário de oração diário": o link na mão e a
    #   resposta dizendo que não tem. Nos turnos em que a frase final saía
    #   certa ("Mandei aqui pra você"), a chamada acontecia mesmo assim — a
    #   equipe de Oração levava um chamado falso a cada pedido de mural.
    #   Não há o que encaminhar num turno em que a entrega já foi feita: o
    #   roteador só assume o turno quando a mensagem É o pedido do mural.
    return OracaoRoute(
        handled=True,
        system_note=(
            "## ⛳ FATO JÁ RESOLVIDO NESTE TURNO — MURAL DE ORAÇÃO\n\n"
            "O mural da oração do dia JÁ FOI ENVIADO para a pessoa por outra "
            "mensagem, junto com os horários e links das Alvoradas. Retorno da "
            f"operação: {resultado}\n\n"
            "\"Calendário de oração\", \"calendário de oração diário\", "
            "\"mural\", \"card\" e \"link de oração\" são todos ESTA MESMA coisa "
            "que acabou de ser entregue. Não existe outro calendário de oração "
            "para pedir a ninguém.\n\n"
            "Sua resposta agora é APENAS uma frase curta e acolhedora "
            "confirmando o envio — algo como \"Mandei aqui pra você 🙏\". "
            "Não repita o link, não descreva o conteúdo, não faça perguntas de "
            "escolha e não ofereça a Alvorada: ela já foi junto. NÃO chame "
            "`notificar_time_interno` e NÃO diga que encaminhou o pedido para "
            "equipe nenhuma: o pedido foi ATENDIDO, não encaminhado."
        ),
        tools_called=["oracao_do_dia"],
        suppress_tools=["oracao_do_dia", "notificar_time_interno"],
        transcript=transcript,
    )
