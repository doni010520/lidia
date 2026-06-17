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

# ── Tools Diacon (Fase 1A) ──

ORACAO_DO_DIA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "oracao_do_dia",
        "description": (
            "Envia o link + card do MOTIVO DE ORAÇÃO DO DIA da igreja (oração CORPORATIVA, "
            "em UNIDADE com a igreja). Use SOMENTE quando a pessoa pede pra orar JUNTO com "
            "a igreja pelo tema do dia: 'qual a oração de hoje?', 'quero orar com vocês', "
            "'me manda o motivo de hoje', 'tem motivo de oração?'. "
            "NÃO use pra pedido pessoal — pra isso use pedido_oracao."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "telefone": {"type": "string", "description": "Telefone do destinatário"},
            },
            "required": ["telefone"],
        },
    },
}

PEDIDO_ORACAO: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "pedido_oracao",
        "description": (
            "Registra um PEDIDO PESSOAL de oração na fila pastoral (Céus Abertos). "
            "Use quando a pessoa quer que ALGUÉM ore POR ELA ou por alguém querido: "
            "'preciso de oração', 'orem por mim', 'minha mãe está doente', "
            "'estou passando por X, ora por mim'. "
            "NÃO use pra oração corporativa do dia — pra isso use oracao_do_dia."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pedido": {
                    "type": "string",
                    "description": "Descrição do pedido (mínimo 2 chars, máx 2000)",
                },
                "nome": {"type": "string", "description": "Nome do solicitante"},
                "telefone": {"type": "string", "description": "Telefone do solicitante"},
            },
            "required": ["pedido"],
        },
    },
}

MINHA_CAMINHADA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "minha_caminhada",
        "description": (
            "Mostra o retrato de engajamento DO PRÓPRIO membro: presenças no ano, "
            "orações registradas, sequências (streaks), 'top X%' e saúde do vínculo. "
            "Use quando a pessoa pergunta sobre a CAMINHADA dela mesma: "
            "'como está minha frequência?', 'quantas vezes orei?', 'minha caminhada', "
            "'como tô indo na igreja?', 'meu engajamento'. "
            "É sobre a PRÓPRIA pessoa — não use pra números gerais da igreja."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "telefone": {"type": "string", "description": "Telefone do membro"},
            },
            "required": ["telefone"],
        },
    },
}

PANORAMA_IGREJA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "panorama_igreja",
        "description": (
            "Panorama GERENCIAL da igreja (membros ativos, células, último domingo, "
            "check-ins, eventos, frequência, saúde). RESTRITO a administradores — a "
            "Diacon só responde se o telefone for de admin. Use quando alguém pede os "
            "números/visão geral da igreja: 'panorama da igreja', 'quantos membros "
            "ativos temos?', 'como estão os números', 'resumo gerencial'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "telefone": {"type": "string", "description": "Telefone de quem pede (admin)"},
            },
            "required": ["telefone"],
        },
    },
}

RESUMO_CELULA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "resumo_celula",
        "description": (
            "Envia o PDF do RESUMO DE PRESENÇA de um encontro da célula (quem da casa "
            "+ visitantes + total). RESTRITO a líderes de célula. Use quando o líder "
            "pede: 'resumo da minha célula', 'presença do encontro', 'quantos foram na "
            "célula', 'relatório de presença da célula'. Diferente do qr_celula (que é "
            "o QR de check-in). Aceita 'data' opcional (YYYY-MM-DD); sem ela, usa o "
            "último encontro com presença."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "telefone": {"type": "string", "description": "Telefone do líder"},
                "data": {"type": "string", "description": "Data do encontro (YYYY-MM-DD), opcional"},
                "group_id": {"type": "string", "description": "ID da célula, se lidera mais de uma"},
            },
            "required": ["telefone"],
        },
    },
}

LINK_FOTO_PERFIL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "link_foto_perfil",
        "description": (
            "Envia um link autenticado (uso único, 30 min) pra membro adicionar "
            "ou atualizar a foto do perfil dele. Use quando a pessoa pede: "
            "'quero atualizar minha foto', 'como mando minha foto?', 'minha foto'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "telefone": {"type": "string", "description": "Telefone do membro"},
            },
            "required": ["telefone"],
        },
    },
}

QR_CELULA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "qr_celula",
        "description": (
            "Envia o PDF do QR Code de presença de uma célula. SOMENTE para líderes "
            "ou líderes em treinamento. Use quando líder pede: 'quero o QR da minha "
            "célula', 'me manda o QR', 'preciso imprimir o QR'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "telefone": {"type": "string", "description": "Telefone do líder"},
                "group_id": {
                    "type": "string",
                    "description": "ID da célula (só se lidera mais de uma)",
                },
            },
            "required": ["telefone"],
        },
    },
}

CELULAS_PROXIMAS: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "celulas_proximas",
        "description": (
            "Lista células públicas mais próximas. Aceita bairro/endereço (campo 'endereco') "
            "OU coordenadas (campos 'lat' e 'lng'). Use quando a pessoa quer encontrar uma célula "
            "perto: 'tem célula perto de mim?', 'qual a célula no bairro X?'. "
            "Se o usuário enviou localização ([LOCALIZAÇÃO] lat=X, lng=Y), passe lat e lng."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "endereco": {
                    "type": "string",
                    "description": "Bairro, região ou endereço (ex: 'Boa Viagem', 'Espinheiro', 'Imbiribeira')",
                },
                "lat": {"type": "number", "description": "Latitude (opcional, se disponível)"},
                "lng": {"type": "number", "description": "Longitude (opcional, se disponível)"},
                "limit": {
                    "type": "integer",
                    "description": "Máximo de resultados (1-20, padrão 5)",
                },
            },
            "required": ["endereco"],
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
    # ── Diacon (Fase 1A) ──
    "oracao_do_dia": ORACAO_DO_DIA,
    "pedido_oracao": PEDIDO_ORACAO,
    "link_foto_perfil": LINK_FOTO_PERFIL,
    "qr_celula": QR_CELULA,
    "celulas_proximas": CELULAS_PROXIMAS,
    "minha_caminhada": MINHA_CAMINHADA,
    "panorama_igreja": PANORAMA_IGREJA,
    "resumo_celula": RESUMO_CELULA,
}


def get_tools(names: list[str]) -> list[dict[str, Any]]:
    """Retorna lista de schemas filtrada pelos nomes permitidos."""
    return [ALL_TOOLS[n] for n in names if n in ALL_TOOLS]
