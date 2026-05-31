"""Registro central de tools.

Cada tool tem um schema OpenAI function-calling e um nome único.
O registry fornece schemas filtrados por agente.
"""
from __future__ import annotations

from typing import Any

# ── Schemas OpenAI ──

BUSCAR_DOCUMENTOS: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "buscar_documentos",
        "description": (
            "Busca informações sobre PAES na base de conhecimento "
            "(ministérios, células, contatos, processos, perguntas gerais). "
            "NÃO usar para eventos (use buscar_evento) nem plano de leitura "
            "(use plano_de_leitura)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Pergunta ou termo a buscar",
                },
            },
            "required": ["query"],
        },
    },
}

CADASTRAR_CONTATO: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "cadastrar_contato",
        "description": (
            "Cadastra novo contato no sistema após coletar nome, email (opcional), "
            "aniversário (opcional) e status."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome completo do contato"},
                "telefone": {"type": "string", "description": "Telefone com DDD"},
                "email": {"type": "string", "description": "Email do contato"},
                "status": {
                    "type": "string",
                    "description": "'membro' ou 'visitante'",
                },
                "aniversario": {
                    "type": "string",
                    "description": "Formato YYYY-MM-DD; se sem ano, usar 2000",
                },
            },
            "required": ["nome", "telefone"],
        },
    },
}

CADASTRAR_ANIVERSARIO: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "cadastrar_aniversario",
        "description": (
            "Registra a data de aniversário PESSOAL do usuário. "
            "NÃO usar para 'aniversário da igreja' (esse é evento)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "telefone": {"type": "string", "description": "Telefone do contato"},
                "data": {
                    "type": "string",
                    "description": "YYYY-MM-DD; sem ano, usar 2000-MM-DD",
                },
            },
            "required": ["telefone", "data"],
        },
    },
}

ATUALIZAR_SOBRENOME: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "atualizar_sobrenome",
        "description": (
            "Atualiza o nome completo do contato após ele informar sobrenome. "
            "Use APENAS quando contexto da conversa indica que a LidIA "
            "perguntou sobre sobrenome."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "telefone": {"type": "string", "description": "Telefone do contato"},
                "nome_completo": {
                    "type": "string",
                    "description": "Nome completo atualizado",
                },
            },
            "required": ["telefone", "nome_completo"],
        },
    },
}

EXCLUIR_USUARIO: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "excluir_usuario",
        "description": (
            "Exclui dados do usuário (LGPD). "
            "SOMENTE chamar após confirmação explícita do usuário."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "telefone": {"type": "string", "description": "Telefone do contato"},
            },
            "required": ["telefone"],
        },
    },
}

BUSCAR_EVENTO: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "buscar_evento",
        "description": (
            "Busca eventos, cultos, celebrações e programações da PAES por data e/ou nome. "
            "USE para qualquer pergunta sobre 'quando', 'que dia', 'horário', 'agenda', "
            "'programação' (exceto plano de leitura bíblica)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_inicio": {"type": "string", "description": "Data inicial YYYY-MM-DD"},
                "data_fim": {"type": "string", "description": "Data final YYYY-MM-DD"},
                "nome_evento": {
                    "type": "string",
                    "description": "Nome ou parte do nome (ex: 'Cursilho', 'Happening')",
                },
            },
            "required": [],
        },
    },
}

PLANO_DE_LEITURA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "plano_de_leitura",
        "description": (
            "Plano de leitura bíblica diário da PAES. USE para 'leitura de hoje', "
            "'qual capítulo ler', 'cronograma', 'em que semana estamos', 'devocional'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "descricao": {
                    "type": "string",
                    "description": "Descrição da dúvida (ex: 'leitura de hoje', 'cronograma da semana')",
                },
            },
            "required": ["descricao"],
        },
    },
}

NOVOS_CONVERTIDOS: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "novos_convertidos",
        "description": "Registra decisão por Cristo do contato.",
        "parameters": {
            "type": "object",
            "properties": {
                "telefone": {"type": "string", "description": "Telefone do contato"},
                "nome": {"type": "string", "description": "Nome do contato"},
            },
            "required": ["telefone", "nome"],
        },
    },
}

PAES_LISTAR_ARQUIVOS: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "PAES_listar_arquivos",
        "description": (
            "Lista arquivos de divulgação (imagens, vídeos, flyers) "
            "disponíveis no Drive da PAES por nome ou evento."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome ou parte do nome do arquivo/evento"},
            },
            "required": ["nome"],
        },
    },
}

PAES_DOWNLOAD_ARQUIVOS: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "PAES_download_arquivos",
        "description": "Envia arquivo de divulgação (imagem/vídeo/flyer) para o WhatsApp do usuário.",
        "parameters": {
            "type": "object",
            "properties": {
                "arquivos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Nomes dos arquivos a enviar",
                },
                "telefone": {"type": "string", "description": "Telefone do destinatário"},
            },
            "required": ["arquivos", "telefone"],
        },
    },
}

ENCAMINHAR_VIDEO_LOUVOR: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "encaminhar_video_louvor",
        "description": "Encaminha vídeo do ministério de louvor recebido do usuário para o responsável.",
        "parameters": {
            "type": "object",
            "properties": {
                "drive_file_id": {"type": "string", "description": "ID do arquivo no Google Drive"},
                "nome": {"type": "string", "description": "Nome do remetente"},
                "telefone": {"type": "string", "description": "Telefone do remetente"},
            },
            "required": ["drive_file_id", "nome", "telefone"],
        },
    },
}

NOTIFICAR_TIME_INTERNO: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "notificar_time_interno",
        "description": (
            "Notifica equipe interna da PAES sobre demanda do usuário "
            "(informações faltantes, pedido de oração, dúvida pastoral, etc)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tipo_situacao": {"type": "string"},
                "prioridade": {"type": "string", "enum": ["baixa", "media", "alta"]},
                "equipe_responsavel": {"type": "string", "description": "Nome da equipe"},
                "nome": {"type": "string"},
                "telefone": {"type": "string"},
                "detalhes": {"type": "string"},
            },
            "required": ["tipo_situacao", "equipe_responsavel", "nome", "telefone", "detalhes"],
        },
    },
}

RESPOSTA_ORACAO: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "resposta_oracao",
        "description": "Registra pedido de oração para envio posterior pela equipe pastoral.",
        "parameters": {
            "type": "object",
            "properties": {
                "Nome": {"type": "string"},
                "Telefone": {"type": "string"},
                "Encorajamento": {"type": "string", "description": "Palavra de encorajamento ou 'sem palavra de encorajamento'"},
            },
            "required": ["Nome", "Telefone", "Encorajamento"],
        },
    },
}

EVENTOS_LIDIA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "eventos_Lidia",
        "description": "ADMIN: cadastra, atualiza ou deleta evento no banco.",
        "parameters": {
            "type": "object",
            "properties": {
                "Nome": {"type": "string"},
                "Descricao": {"type": "string"},
                "Local": {"type": "string"},
                "Data_inicio": {"type": "string"},
                "Data_final": {"type": "string"},
                "Hora": {"type": "string"},
                "Valor": {"type": "string"},
                "Link": {"type": "string"},
                "funcao": {"type": "string", "enum": ["cadastrar", "atualizar", "deletar"]},
                "media": {"type": "string"},
            },
            "required": ["Nome", "funcao"],
        },
    },
}

INFORMACOES_LIDIA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "informacoes_Lidia",
        "description": "ADMIN: cadastra, atualiza ou deleta par pergunta-resposta na base de conhecimento.",
        "parameters": {
            "type": "object",
            "properties": {
                "Pergunta": {"type": "string"},
                "Resposta": {"type": "string"},
                "funcao": {"type": "string", "enum": ["cadastrar", "atualizar", "deletar"]},
            },
            "required": ["Pergunta", "Resposta", "funcao"],
        },
    },
}

TREINAMENTO_LIDIA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "treinamento_LidIA",
        "description": "ADMIN: dispara re-vectorização completa da base de conhecimento.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

# ── Mapa completo ──

ALL_TOOLS: dict[str, dict[str, Any]] = {
    "buscar_documentos": BUSCAR_DOCUMENTOS,
    "buscar_evento": BUSCAR_EVENTO,
    "plano_de_leitura": PLANO_DE_LEITURA,
    "cadastrar_contato": CADASTRAR_CONTATO,
    "cadastrar_aniversario": CADASTRAR_ANIVERSARIO,
    "atualizar_sobrenome": ATUALIZAR_SOBRENOME,
    "excluir_usuario": EXCLUIR_USUARIO,
    "novos_convertidos": NOVOS_CONVERTIDOS,
    "PAES_listar_arquivos": PAES_LISTAR_ARQUIVOS,
    "PAES_download_arquivos": PAES_DOWNLOAD_ARQUIVOS,
    "encaminhar_video_louvor": ENCAMINHAR_VIDEO_LOUVOR,
    "notificar_time_interno": NOTIFICAR_TIME_INTERNO,
    "resposta_oracao": RESPOSTA_ORACAO,
    "eventos_Lidia": EVENTOS_LIDIA,
    "informacoes_Lidia": INFORMACOES_LIDIA,
    "treinamento_LidIA": TREINAMENTO_LIDIA,
}


def get_tools(names: list[str]) -> list[dict[str, Any]]:
    """Retorna lista de schemas filtrada pelos nomes permitidos."""
    return [ALL_TOOLS[n] for n in names if n in ALL_TOOLS]
