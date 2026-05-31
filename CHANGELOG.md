# Changelog

## [1.2.0] — Gestão de Eventos (Fase B)

### Adicionado
- `GET /api/eventos` — listagem com filtros `periodo` (futuros/passados/todos) e `origem` (painel/sheets/todos)
- `POST /api/eventos` — criação com `origem=painel` e `sheets_row_id=painel:<uuid>`
- `PATCH /api/eventos/{id}` — edição com proteção de conflito Sheets (409 + `confirmar_descolar`)
- `DELETE /api/eventos/{id}` — exclusão com mesma proteção de conflito
- `POST /api/eventos/upload-capa` — upload de imagem para Google Drive
- Migration `005_eventos_origem.sql` — coluna `origem` em `eventos_paes`
- Frontend: aba "Eventos" com form CRUD, tabela com filtros, chip de origem, upload de capa
- `tests/test_eventos_api.py` — 6 testes cobrindo CRUD + conflito 409

### Modificado
- `app/models/eventos.py` — campo `origem` adicionado com CHECK constraint
- `app/main.py` — registro do router de eventos
- `app/static/index.html` — aba Eventos adicionada ao painel
- `README.md` — seção de Gestão de Eventos documentada

## [1.1.0] — Disparos em Massa (Fase A)

### Adicionado
- `POST /api/auth/login` — autenticação JWT
- `GET /api/disparos` — listagem
- `POST /api/disparos` — criação (imediato ou agendado)
- `PATCH /api/disparos/{id}/cancelar` — cancelamento
- `GET /api/disparos/{id}/log` — log de envio paginado
- `POST /api/disparos/upload` — upload de arquivo para Drive
- `GET /api/disparos/contatos-count` — preview de contatos elegíveis
- Worker `disparo_runner` com toggle de chatbot, idempotência, anti-spam 3s
- Worker `disparo_scheduler` (APScheduler 1min)
- Frontend: painel com login, upload drag/drop, histórico com progresso
- Migration `003_disparos.sql` — tabelas disparos, disparo_log, usuarios_painel
- Anonimização LGPD em `excluir_usuario` (disparo_log)
- 27 testes

## [1.0.0] — LidIA Core

### Adicionado
- Pipeline conversacional: webhook → buffer Redis → RAG → OpenAI → WhatsApp
- 16 tools de function-calling (13 atendimento + 3 admin)
- Media processor: áudio (Whisper), imagem (GPT Vision), PDF/DOCX/XLSX/PPTX, vídeo (Drive)
- Handoff dual: pausa automática 30min + toggle persistente por keyword
- Analytics: tokens, custo, intent, sentimento
- Workers: sheets_sync (15min), oração (5min)
- Admin router: prefixos TreinoIA12, AgendaIA12, Limpar dados
- 156 testes
