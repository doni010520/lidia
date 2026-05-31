# LidIA — Assistente Virtual da PAES

Assistente de IA para WhatsApp da Paróquia Anglicana Espírito Santo (PAES), migrando de n8n para FastAPI standalone.

## Arquitetura

```
WhatsApp → uazapi v2 webhook → FastAPI → Buffer Redis (10s debounce)
  → Contact lookup → Media decrypt → Admin check → RAG pré-busca
  → OpenAI GPT-4.1-mini (tool loop) → Analytics → Envio em partes

Painel Web (/) → Auth JWT → Disparos em Massa / Gestão de Eventos
```

## Stack

- **API**: FastAPI + Uvicorn
- **LLM**: OpenAI GPT-4.1-mini (tool-calling)
- **RAG**: pgvector (1536d, text-embedding-3-small)
- **DB**: PostgreSQL 16 + pgvector
- **Cache**: Redis 7 (debounce + dedup)
- **WhatsApp**: uazapi v2
- **Google**: Sheets API + Drive API + Gmail API
- **Workers**: APScheduler (sheets sync 15min, oração 5min, disparo scheduler 1min)
- **Auth**: bcrypt + JWT (painel web)
- **Frontend**: SPA vanilla (HTML/CSS/JS inline)

## Setup local

```bash
# 1. Configurar
cp .env.example .env
# Editar .env com credenciais reais

# 2. Subir infra
docker compose up -d

# 3. Migrations
docker compose exec db psql -U lidia -d lidia -f /app/migrations/001_lidia_schema.sql
docker compose exec db psql -U lidia -d lidia -f /app/migrations/002_unique_eventos.sql
docker compose exec db psql -U lidia -d lidia -f /app/migrations/003_disparos.sql
docker compose exec db psql -U lidia -d lidia -f /app/migrations/005_eventos_origem.sql

# 4. Seeds
docker compose exec app python -m scripts.seed_equipes
docker compose exec app python -m scripts.seed_admin

# 5. Indexar base de conhecimento
docker compose exec app python -m scripts.index_knowledge --path /app/docs/ --clear

# 6. Acessar painel
# http://localhost:8000/ → login → Disparos / Eventos
```

## Painel Web

Acesso em `/` com autenticação JWT.

### Disparos em Massa
- Upload de arquivo (imagem/PDF/vídeo) para Google Drive
- Legenda + filtro de contatos (todos/membros/visitantes)
- Envio imediato ou agendado (horário comercial Seg-Sex 7:30-18, Sáb 8-13)
- Lock global: 1 disparo ativo por vez
- Anti-spam: delay de 3s entre envios
- Toggle automático de chatbot_stop durante envio
- Histórico com barra de progresso em tempo real
- Cancelamento mid-loop

### Gestão de Eventos
- CRUD de eventos (substituindo Google Sheets)
- Upload de capa para Google Drive
- Filtro por período (futuros/passados/todos) e origem (painel/sheets/todos)
- Proteção de eventos vindos da planilha: editar/excluir exige confirmação de "descolar"
- Chip visual diferenciando origem (painel vs planilha)

## Tools disponíveis (16)

### Atendimento (13) — agente principal
| Tool | Descrição |
|---|---|
| buscar_documentos | RAG na base de conhecimento |
| buscar_evento | SQL + fallback RAG |
| plano_de_leitura | Leitura bíblica por data/semana |
| cadastrar_contato | UPSERT de contato |
| cadastrar_aniversario | Atualiza aniversário |
| atualizar_sobrenome | Atualiza nome completo |
| excluir_usuario | Delete LGPD (com anonimização de disparo_log) |
| novos_convertidos | Registra decisão por Cristo |
| PAES_listar_arquivos | Lista arquivos do Drive |
| PAES_download_arquivos | Envia arquivos via WhatsApp |
| encaminhar_video_louvor | Encaminha vídeo para equipe |
| notificar_time_interno | WhatsApp + email + Sheets log |
| resposta_oracao | Registra pedido na fila |

### Admin (3) — via prefixo
| Prefixo | Tool |
|---|---|
| TreinoIA12 / BaseIA12 | treinamento_LidIA |
| AgendaIA12 | eventos_Lidia |
| Limpar dados | Limpeza LGPD |

## Handoff humano

Dois mecanismos combinados:
1. **Pausa automática (30min)**: uazapi pausa quando humano envia mensagem
2. **Toggle persistente**: "Roberta aqui!" → desativa, "té mais!" → reativa

## Testes

```bash
python -m pytest tests/ -v
```

## Deploy (Easypanel)

1. Push para GitHub (`doni010520/lidia`)
2. Easypanel auto-deploy
3. Verificar `/health` e `/ready`
4. Apontar webhook da uazapi para `https://<domain>/webhook`

## Variáveis de ambiente

Ver `.env.example` para lista completa.
