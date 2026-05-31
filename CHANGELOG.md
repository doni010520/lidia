# Changelog

Histórico de entregas da migração da LidIA (n8n → Python/FastAPI).

## [1.0.0] — Migração completa

Sistema pronto para produção. **156 testes passando**, todas as 10 fases concluídas.

### Fase 1 — Infraestrutura e Webhook
- FastAPI app com lifespan + APScheduler
- Cliente uazapi v2 completo (`uaz_client.py`)
- Webhook handler com HMAC, dedup, filtro de grupos/revoke/from_me
- Buffer Redis com debounce de 10s
- Schema do banco (9 tabelas) + models SQLAlchemy
- 14 testes unitários

### Fase 1-v2 — Correções
- Nomes corretos de campos uazapi v2 (`id` em vez de `messageId`, `replyid` em vez de `replyId`)
- Tratamento de envelope `body` no webhook
- Cobertura de JID `@lid`
- 16 testes adicionados

### Fase 2 — Agente principal sem tools
- Pipeline de conversação completo (14 etapas)
- RAG service (pgvector + retrieve_hint)
- OpenAI service com tool-calling loop
- Agentes LidIA e LidIA_cadastro com renderização de system prompt via `str.replace`
- Script `index_knowledge.py` para PDF/DOCX/XLSX/PPTX
- 52 testes

### Fase 3 — Tools de CRM
- Registry + dispatcher de tools
- Tools: `buscar_documentos`, `cadastrar_contato`, `cadastrar_aniversario`, `atualizar_sobrenome`, `excluir_usuario`
- Commit imediato para contatos novos + atualização de nome quando vazio
- `json.dumps` para metadata
- 87 testes

### Fase 4 — Tools de conteúdo + Sheets sync
- Tools: `buscar_evento`, `plano_de_leitura`, `novos_convertidos`
- Cliente Google Sheets + 3 workers de sync (eventos, plano, informações)
- Integração APScheduler
- 104 testes

### Fase 5 — Mídia e arquivos
- `media_processor` com decrypt via uazapi (áudio + imagem + PDF/DOCX/XLSX/PPTX + vídeo)
- Cliente Google Drive (search/upload/share/public_url)
- Tools: `PAES_listar_arquivos`, `PAES_download_arquivos`, `encaminhar_video_louvor`
- Migration 002 com UNIQUE constraint para `sheets_row_id`
- 125 testes

### Fase 6 — Notificações e oração
- Cliente Gmail
- Tool `notificar_time_interno` com fallback "Dúvidas Gerais"
- Tool `resposta_oracao` com cascade para notificar Pastoral
- Worker `oracao_responder` a cada 5min
- Seed das 17 equipes

### Fase 7 — Roteamento admin
- `admin_router` com 5 prefixos (TreinoIA12 / AgendaIA12 / ArquivosIA12 / Resposta_oracaoIA12 / Limpar dados)
- Tools admin: `eventos_Lidia`, `informacoes_Lidia`, `treinamento_LidIA`
- Integração no `conversation_service` (passo 2.5 do pipeline)

### Fase 8 — Handoff e analytics
- `handoff_service` com regex "Roberta aqui!" / "té mais!"
- Pausa nativa uazapi configurada no lifespan
- `analytics_service` com tokens, custo, intent, sentimento
- 144 testes

### Fase 9 — Migração Supabase
- Script `migrate_from_supabase.py` com `--dry-run` e `--include-history`
- 4 migrate functions: contacts, novos_convertidos, eventos, plano_leitura
- UPSERT idempotente com COALESCE

### Fase 10 — README e documentação
- README com arquitetura, stack, setup, deploy
- 156 testes finais
- Pronto para go-live

---

## Stack final

- **API:** FastAPI + Uvicorn
- **LLM:** OpenAI gpt-4.1-mini (tool-calling)
- **RAG:** pgvector (1536d, text-embedding-3-small)
- **DB:** PostgreSQL 16 + pgvector
- **Cache:** Redis 7 (debounce + dedup)
- **WhatsApp:** uazapi v2
- **Google:** Sheets API + Drive API + Gmail API
- **Workers:** APScheduler (sheets sync 15min, oração 5min)
- **Auth:** bcrypt + JWT (planejado para módulo Disparos)
