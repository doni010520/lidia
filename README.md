# LidIA — Assistente Virtual da PAES

Assistente de IA para WhatsApp da Paróquia Anglicana Espírito Santo (PAES), migrando de n8n para FastAPI standalone.

## Arquitetura

```
WhatsApp → uazapi v2 webhook → FastAPI → Buffer Redis (10s debounce)
  → Contact lookup → Media decrypt → Admin check → RAG pré-busca
  → OpenAI GPT-4.1-mini (tool loop) → Analytics → Envio em partes
```

## Stack

- **API**: FastAPI + Uvicorn
- **LLM**: OpenAI GPT-4.1-mini (tool-calling)
- **RAG**: pgvector (1536d, text-embedding-3-small)
- **DB**: PostgreSQL 16 + pgvector
- **Cache**: Redis 7 (debounce + dedup)
- **WhatsApp**: uazapi v2
- **Google**: Sheets API + Drive API + Gmail API
- **Workers**: APScheduler (sheets sync 15min, oração 5min)

## Setup local

```bash
# 1. Configurar
cp .env.example .env
# Editar .env com credenciais reais

# 2. Subir infra
docker compose up -d

# 3. Popular equipes
docker compose exec app python -m scripts.seed_equipes

# 4. Indexar base de conhecimento
docker compose exec app python -m scripts.index_knowledge --path /app/docs/ --clear

# 5. (Opcional) Migrar dados do Supabase
SUPABASE_URL=... SUPABASE_KEY=... docker compose exec app python -m scripts.migrate_from_supabase --dry-run
SUPABASE_URL=... SUPABASE_KEY=... docker compose exec app python -m scripts.migrate_from_supabase
```

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
| excluir_usuario | Delete LGPD (com confirmação) |
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
# Rodar todos
python -m pytest tests/ -v

# Com cobertura
python -m pytest tests/ --cov=app --cov-report=term-missing
```

## Deploy (Easypanel)

1. Push para GitHub (`doni010520/lidia`)
2. Easypanel auto-deploy
3. Verificar `/health` e `/ready`
4. Apontar webhook da uazapi para `https://<domain>/webhook`

## Variáveis de ambiente

Ver `.env.example` para lista completa.

## Inicializar repositório Git

Se ainda não está versionado, dentro da pasta do projeto:

```bash
git init
git add .
git commit -m "feat: LidIA v1.0 — migração completa de n8n para FastAPI"
git branch -M main
git remote add origin git@github.com:doni010520/lidia.git
git push -u origin main
```

> O `.gitignore` já cobre `__pycache__/`, `.env`, `secrets/`, caches, dados de banco
> e service accounts do Google. Confira antes do primeiro commit que nenhum
> arquivo sensível foi adicionado: `git status` + `git diff --stat`.

## Estrutura do projeto

```
lidia/
├── app/
│   ├── agents/           # LidIA (lead existente) + LidIA_cadastro (lead novo)
│   ├── api/              # /webhook + /health + /ready
│   ├── core/             # config (pydantic-settings)
│   ├── models/           # ORM SQLAlchemy
│   ├── prompts/          # system prompts (75KB para LidIA principal)
│   ├── routers/          # admin_router (prefixos TreinoIA12 etc)
│   ├── schemas/          # Pydantic (UAZWebhookPayload, IncomingMessage)
│   ├── services/         # uaz_client, drive_client, rag_service, etc
│   ├── tools/            # 16 tools + registry + dispatcher
│   ├── workers/          # sheets_sync, oracao_responder
│   ├── db.py             # engine async + session factory
│   └── main.py           # FastAPI + lifespan + APScheduler
├── migrations/           # 001_lidia_schema + 002_unique_eventos
├── scripts/              # index_knowledge, migrate_from_supabase, seed_equipes
├── tests/                # 156 testes, suite passa em ~25s
├── docker-compose.yml    # db (pgvector) + redis + app
├── Dockerfile
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .gitignore
├── CHANGELOG.md
├── LICENSE               # MIT
└── README.md
```

## Cobertura de testes

156 testes passando, distribuídos em:

- `test_webhook_parser.py` (16) — parse uazapi v2 + JID + dedup
- `test_uaz_client.py` (14) — endpoints + campos corretos (id, replyid)
- `test_buffer.py` (8) — debounce Redis + agregação
- `test_rag.py` (8) — busca vetorial + retrieve_hint
- `test_conversation_flow.py` (10) — pipeline + render de prompt
- `test_index_knowledge.py` (6) — chunking + json.dumps
- `test_migration.py` (5) — script de migração
- `test_tools/test_tools_handlers.py` (25) — 5 tools de CRM
- `test_tools/test_fase4_tools.py` (18) — buscar_evento, plano, sheets_sync
- `test_tools/test_fase5_media.py` (19) — media_processor (decrypt + Vision)
- `test_tools/test_fase678.py` (20) — notificar, oração, handoff, analytics
- `test_tools/test_admin_bugs.py` (7) — anti-regressão admin + eventos_lidia
