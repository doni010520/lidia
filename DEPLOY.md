# Deploy — LidIA na VPS (EasyPanel)

Guia passo-a-passo para subir a LidIA em produção via EasyPanel + apontar o webhook da uazapi v2.

---

## 1. Pré-requisitos (operador precisa ter em mãos)

| Item | Onde obter |
|---|---|
| OpenAI API Key | platform.openai.com/api-keys |
| uazapi v2 — Base URL + Token da instância PAES | painel uazapi |
| Service Account JSON do Google (Drive + Sheets + Gmail) | console.cloud.google.com → APIs & Services → Credentials |
| IDs das pastas do Drive (`DRIVE_FOLDER_DOCUMENTS` + `DRIVE_FOLDER_MEDIA`) | URLs das pastas no Drive |
| IDs das planilhas Sheets (eventos, info, plano de leitura, log notificações, log oração) | URLs das planilhas |
| Email do remetente Gmail | conta de serviço configurada |
| Lista de telefones admin (operadores autorizados a usar `TreinoIA12` etc) | acordo interno |
| Senha do primeiro usuário do painel web | escolher na hora |

---

## 2. Setup no EasyPanel

### 2.1 Criar o projeto
- **EasyPanel → New Project → "lidia"**
- 3 serviços dentro do projeto: `db`, `redis`, `app`

### 2.2 Serviço `db` (PostgreSQL com pgvector)
- **Template:** Postgres
- **Image:** `pgvector/pgvector:pg16` (sobrescrever a imagem padrão)
- **Env vars:**
  - `POSTGRES_USER=lidia`
  - `POSTGRES_PASSWORD=<senha-forte-gerada>` ← guardar
  - `POSTGRES_DB=lidia`
- **Volume:** `pgdata` mapeado em `/var/lib/postgresql/data`
- **Não** expor porta externamente (só interna)

> O EasyPanel **NÃO** vai aplicar os scripts SQL automaticamente como o
> docker-compose. Você vai aplicá-los manualmente após o serviço subir
> (ver passo 4).

### 2.3 Serviço `redis`
- **Template:** Redis
- **Image:** `redis:7-alpine`
- **Não** expor porta externamente

### 2.4 Serviço `app` (FastAPI)
- **Source:** GitHub `doni010520/lidia` (branch `main`)
- **Build:** Dockerfile (na raiz do repo)
- **Port:** 8000
- **Domain:** `lidia.seudominio.com.br` (apontar DNS A/CNAME para o IP do EasyPanel)
- **HTTPS:** Let's Encrypt automático
- **Env vars:** colar o conteúdo do `.env.example` preenchido (ver passo 3)
- **Mounts:** criar pasta `secrets` no host EasyPanel, montar em `/app/secrets`
  e fazer upload do JSON do Google service account lá

---

## 3. Variáveis de ambiente (.env do serviço `app`)

Copiar do `.env.example` e preencher:

```bash
# Identidade
AGENT_NAME=LidIA
ENV=production
DEBUG=false
LOG_LEVEL=INFO

# OpenAI
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4.1-mini
OPENAI_TEMPERATURE=0.5
OPENAI_MAX_TOKENS=2000
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# uazapi v2 (PRODUÇÃO)
UAZ_BASE_URL=https://<instancia>.uazapi.com
UAZ_TOKEN=<token-da-instancia>
UAZ_WEBHOOK_SECRET=

# Database (nome do serviço EasyPanel = hostname interno)
DATABASE_URL=postgresql+asyncpg://lidia:<senha-do-db>@db:5432/lidia
REDIS_URL=redis://redis:6379/0
REDIS_BUFFER_SECONDS=10

# Conversa
HISTORY_LIMIT=40
RAG_ENABLED=true
RAG_TOP_K=7

# Google (montar JSONs em /app/secrets)
GOOGLE_SERVICE_ACCOUNT_JSON=/app/secrets/google-sa.json
DRIVE_FOLDER_DOCUMENTS=<id-da-pasta-docs>
DRIVE_FOLDER_MEDIA=<id-da-pasta-midia>
SHEETS_EVENTOS_ID=<id-planilha>
SHEETS_INFORMACOES_ID=<id-planilha>
SHEETS_PLANO_LEITURA_ID=<id-planilha>
SHEETS_LOG_NOTIFICACOES_ID=<id-planilha>
SHEETS_LOG_ORACAO_ID=<id-planilha>

# Gmail
GMAIL_FROM=lidia@paes.org.br
GMAIL_SERVICE_ACCOUNT_JSON=/app/secrets/gmail-sa.json

# Admin (números que podem usar prefixos TreinoIA12, etc)
ADMIN_PHONES=5581XXXXXXXXX,5581YYYYYYYYY

# Handoff humano (Roberta aqui! / té mais!)
HANDOFF_PAUSE_MINUTES=30
HANDOFF_KEYWORD_OFF=Roberta aqui!
HANDOFF_KEYWORD_ON=té mais!

# Workers
TRAINING_SCHEDULE_CRON=0 3 * * *
SHEETS_SYNC_INTERVAL_MINUTES=15

# Disparos
DISPAROS_DELAY_SECONDS=3
DISPAROS_BUSINESS_HOURS_ENABLED=true
DISPAROS_MAX_FILE_MB=16
DISPAROS_DRIVE_FOLDER=

# Auth do painel web (Disparos + Eventos)
PAINEL_JWT_SECRET=<gerar-string-aleatoria-32-chars>   # openssl rand -hex 32
PAINEL_JWT_EXPIRE_HOURS=12
PAINEL_DEFAULT_ADMIN_USER=admin
PAINEL_DEFAULT_ADMIN_PASS=                             # deixar vazio — o seed pede

# Misc
DRY_RUN=false
```

---

## 4. Aplicar migrations + seed (uma única vez)

Após o serviço `db` estar `healthy` e o `app` rodando, executar dentro
do container `app` (via terminal do EasyPanel):

```bash
# 1. Aplicar todas as migrations em ordem
psql "$DATABASE_URL" -f migrations/001_lidia_schema.sql
psql "$DATABASE_URL" -f migrations/002_unique_eventos.sql
psql "$DATABASE_URL" -f migrations/003_disparos.sql
psql "$DATABASE_URL" -f migrations/005_eventos_origem.sql

# Confirmar que pgvector e todas as tabelas existem
psql "$DATABASE_URL" -c "\dx"
psql "$DATABASE_URL" -c "\dt"

# 2. Popular as 17 equipes responsáveis (pastoral, louvor, etc.)
python -m scripts.seed_equipes

# 3. Criar o primeiro usuário do painel web (interativo — pede senha)
python -m scripts.seed_admin

# 4. Indexar a base de conhecimento (PDFs e DOCXs no DRIVE_FOLDER_DOCUMENTS)
python -m scripts.index_knowledge --path /app/docs/ --clear
# OU se já tiver os documentos no Drive e o sync vai pegar:
# (a próxima execução do worker sheets_sync vai puxar)

# 5. (OPCIONAL) Migrar dados do Supabase antigo
SUPABASE_URL=https://xxxx.supabase.co \
SUPABASE_KEY=eyJ... \
  python -m scripts.migrate_from_supabase --dry-run
# Validar contagens, depois rodar sem --dry-run
```

---

## 5. Configurar o webhook na uazapi v2

No painel da uazapi:

```
URL do webhook: https://lidia.seudominio.com.br/webhook
Eventos a enviar:
  ✅ messages
  ✅ messages_update      (opcional)
  ✅ connection           (opcional, só pra logging)
Excluir mensagens:
  (nenhum filtro — o app filtra grupos e fromMe internamente)
```

E enquanto estiver lá, na seção **ChatBot Settings**:
```
chatbot_enabled: true
chatbot_ignore_groups: true
chatbot_stop_when_you_send_msg: 30   (handoff humano automático)
```

> Esses 3 settings o próprio app reaplica no startup via `update_chatbot_settings`,
> mas vale conferir manualmente que a uazapi aceitou.

---

## 6. Validar deploy

Em ordem:

```bash
# 1. Health check
curl https://lidia.seudominio.com.br/health
# → {"status": "ok"}

# 2. Ready check (testa Postgres + Redis)
curl https://lidia.seudominio.com.br/ready
# → {"status": "ready", "checks": {"redis": "ok", "postgres": "ok"}}

# 3. Acessar painel web
# Abrir https://lidia.seudominio.com.br/ no navegador
# Login com o usuário criado em "seed_admin"
# Conferir que abre as abas "Disparos" e "Eventos"
```

### Smoke test no WhatsApp
Mandar uma mensagem pelo número conectado à uazapi:
- Texto simples: "Oi, quando é o próximo culto?"
- Esperar: LidIA responde em até ~15s (10s debounce + ~5s LLM)
- Conferir logs no EasyPanel para ver o pipeline rodando

### Comando admin de teste (de um número da `ADMIN_PHONES`)
```
Limpar dados
```
Esperar: confirmação de que o histórico foi apagado.

---

## 7. Desligar o n8n (cutover)

**Só depois** dos validações acima passarem:

1. No painel n8n: **desativar** o workflow `yLwKAe3oggbCIbRn` (LidIA PAES)
2. Confirmar que o webhook antigo `/paes` parou de receber tráfego (a uazapi
   agora aponta só para o novo `/webhook` da VPS)
3. Manter o n8n no ar por **7 dias** desativado (rollback rápido se algo der errado)
4. Após 7 dias estáveis: arquivar o workflow

---

## 8. Rollback de emergência

Se algo crítico der errado:

```
1. No painel uazapi: apontar webhook de volta para a URL antiga do n8n
2. No n8n: reativar workflow yLwKAe3oggbCIbRn
3. Investigar o problema no EasyPanel sem pressa
```

O Postgres novo continua intacto — quando voltar a usar, é só apontar o
webhook de novo. Histórico de mensagens da janela do rollback fica registrado
no n8n e pode ser sincronizado depois.

---

## 9. Monitoramento contínuo

EasyPanel já mostra logs em tempo real. Olhar regularmente:

- **Latência de resposta:** logs do `conversation_service` mostram quantos ms
- **Custo OpenAI:** tabela `llm_analytics` (`SELECT SUM(cost_usd) FROM llm_analytics WHERE created_at > NOW() - INTERVAL '7 days'`)
- **Disparos:** painel web → aba Disparos mostra histórico + falhas
- **Workers:** logs do APScheduler mostram quando rodou cada job

---

## 10. Manutenção

- **Subir nova versão:** push em `main` no GitHub → EasyPanel auto-rebuilds
- **Aplicar nova migration:** rodar `psql "$DATABASE_URL" -f migrations/00X_*.sql` no terminal do container
- **Trocar tema visual:** editar `app/static/index.html` e commitar (paleta roxa é a oficial — ver CHANGELOG)
- **Backup do Postgres:** EasyPanel tem backup automático configurável; alternativa: `pg_dump` agendado via cron no host

---

## Suporte

Qualquer problema, abrir issue em `https://github.com/doni010520/lidia/issues`.
