# Módulo de Eventos — LidIA PAES

Como a PAES gerencia a agenda de eventos hoje, da entrada do dado até a entrega
no WhatsApp pelo bot. Documenta o estado atual (pré-migração Diacon).

---

## 1. Visão geral

A LidIA precisa responder perguntas como *"que dia tem culto?"*,
*"quando vai ter Cursilho?"*, *"tem evento essa semana?"*. Pra isso, existe
um catálogo de eventos no Postgres da LidIA, alimentado por **três fontes**, e
exposto por **três interfaces de consumo**.

```
       ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
ENTRADA│ Google Sheets    │    │ Painel /eventos  │    │ Gerador (SQL)    │
       │ (planilha legada)│    │ (admin web)      │    │ cultos dominicais│
       └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
                │                       │                       │
                ▼                       ▼                       ▼
              ┌─────────────────────────────────────────────────────┐
   POSTGRES   │             tabela eventos_paes                     │
              │       (com coluna `origem` discriminando)           │
              └─────────────────────────────────────────────────────┘
                │                       │                       │
                ▼                       ▼                       ▼
       ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
SAÍDA  │ LidIA WhatsApp   │    │ Painel /eventos  │    │ Worker            │
       │ (buscar_evento)  │    │ (listagem CRUD)  │    │ (aniversariantes  │
       │                  │    │                  │    │  recebem citação) │
       └──────────────────┘    └──────────────────┘    └──────────────────┘
```

---

## 2. Modelo de dados

Tabela `eventos_paes` (`app/models/eventos.py`):

| Campo | Tipo | Notas |
|---|---|---|
| `id` | `integer` PK | autoincrement |
| `nome` | `text` *(obrigatório)* | título do evento |
| `descricao` | `text` | descrição livre |
| `local` | `text` | endereço ou nome do espaço |
| `data_inicio` | `date` *(obrigatório)* | quando começa |
| `data_final` | `date` | quando termina (pode ser igual a `data_inicio`) |
| `hora` | `text` | **texto livre** — `"18h"`, `"10h às 12h"`, `"manhã"` |
| `valor` | `text` | `"Gratuito"`, `"R$ 50,00"`, etc. |
| `link` | `text` | URL de inscrição |
| `media` | `text` | URL da capa (imagem) |
| `sheets_row_id` | `text` *(único)* | rastreio quando vem de planilha ou gerador |
| `origem` | `text` *(check)* | `"sheets"` &#124; `"painel"` &#124; `"gerador"` |
| `created_at`, `updated_at` | `timestamptz` | gerenciados pelo DB |

**Decisão importante — `hora` é texto:** a planilha PAES tinha valores
heterogêneos ("18hrs", "manhã", "10h às 12h"). Forçar `TIME` faria a migração
quebrar em ~30% das linhas. Texto livre é mais leal ao operador e o
front-end já valida no display.

---

## 3. As três fontes de entrada

### 3.1 Google Sheets (legado)

- Planilha: `SHEETS_EVENTOS_ID` (env var,
  ID `1J3KJfuvuOsi5LGFgEm9gylzZJWRssBjaz6bfq9YivaQ`)
- Worker `sheets_sync` (`app/workers/sheets_sync.py`) lê via proxy n8n
  a cada **15 minutos** (`SHEETS_SYNC_INTERVAL_MINUTES`).
- Cada linha vira um upsert em `eventos_paes` com `origem = 'sheets'`
  e `sheets_row_id = f"sheets:{linha_id}"`.
- A planilha continua sendo a "interface de edição" pra quem não usa o painel.
- **Quem prefere usar?** A equipe pastoral antiga e algumas secretárias que
  já tinham o fluxo no Google Drive.

### 3.2 Painel `/eventos` (web)

- Página dedicada (`app/static/eventos.html`) com formulário completo.
- Cria → `POST /api/eventos` com `origem = 'painel'`.
- Edita → `PATCH /api/eventos/{id}`.
- Deleta → `DELETE /api/eventos/{id}`.
- Upload de capa → `POST /api/eventos/upload-capa` (gera URL no Drive PAES
  via proxy n8n).
- **Conflito:** se você edita ou deleta um evento que veio do Sheets, a API
  retorna `409 Conflict` com `error: "evento_de_planilha"` e mensagem
  pedindo confirmação. A UI mostra um diálogo "descolar da planilha?".
  Se confirma (`confirmar_descolar: true`), o evento muda `origem` para
  `'painel'` e o `sheets_sync` para de mexer nele.

### 3.3 Gerador (SQL function)

- Function PostgreSQL `gerar_cultos_dominicais(meses integer)`
  (`migrations/006_atendimentos_e_funcoes.sql`).
- Worker `cultos_gerador` (`app/workers/cultos_gerador.py`) roda
  **todo dia 1 do mês, 1h da manhã (BR)** e chama
  `SELECT gerar_cultos_dominicais(3)` — popula automaticamente os
  cultos dominicais dos próximos 3 meses (`CULTOS_DOMINICAIS_MESES_A_FRENTE`).
- Para cada domingo gera 3 cultos (8h, 10h, 17h), com `origem = 'gerador'`
  e `sheets_row_id = 'auto:culto-dom:YYYY-MM-DD:HH'`.
- Idempotente: `ON CONFLICT (sheets_row_id) DO NOTHING`.

---

## 4. Workers no scheduler

| Worker | Frequência | O que faz |
|---|---|---|
| `sheets_sync` | a cada 15 min | puxa eventos da planilha → upsert |
| `cultos_gerador` | dia 1 do mês, 01h BR | gera cultos dominicais dos próximos 3 meses |

Agendados em `app/main.py` (lifespan startup) via APScheduler. Todos os
horários considerados em America/Sao_Paulo.

---

## 5. APIs REST (`/api/eventos`)

Endpoint principal do painel. Todos exigem JWT do painel
(`Authorization: Bearer <token>`).

| Método | Rota | Função |
|---|---|---|
| `GET` | `/api/eventos` | lista; filtros `?periodo=futuros\|passados\|todos` e `?origem=painel\|sheets\|todos` |
| `POST` | `/api/eventos` | cria com `origem='painel'` |
| `PATCH` | `/api/eventos/{id}` | edita; conflita se `origem='sheets'` (a menos que `confirmar_descolar=true`) |
| `DELETE` | `/api/eventos/{id}` | deleta; mesma regra de conflito |
| `POST` | `/api/eventos/upload-capa` | recebe `multipart/form-data`, salva no Drive PAES, devolve URL pública |

Schemas Pydantic em `app/schemas/eventos.py`.

---

## 6. Tools da LidIA (function calling do LLM)

A LidIA tem 2 tools que tocam eventos. O LLM decide qual chamar com base
na intenção do usuário.

### 6.1 `buscar_evento` — leitura

**Quando o LLM chama:** qualquer pergunta sobre "quando", "que dia",
"horário", "agenda", "programação" (exceto plano de leitura bíblica).

**Args:**
```json
{
  "data_inicio": "2026-06-04",        // opcional, YYYY-MM-DD
  "data_fim": "2026-06-11",           // opcional
  "nome_evento": "Cursilho"           // opcional, busca parcial
}
```

**Implementação** (`app/tools/tool_modules/buscar_evento.py`):
- Sem filtros → próximos 60 dias.
- Filtro por nome → `ILIKE %nome%`.
- Retorno formatado em texto pro LLM compor a resposta:
  ```
  📌 Cursilho Masculino | Data: 28/05/2026 a 31/05/2026 | Local: ...
  ```

### 6.2 `eventos_Lidia` — escrita (admin)

**Quando o LLM chama:** **somente** quando o telefone do remetente é
de um administrador (lista `ADMIN_TOOLS` em `app/agents/lidia.py`).

**Args:**
```json
{
  "funcao": "cadastrar" | "atualizar" | "deletar",
  "Nome": "Cursilho Masculino",
  "Descricao": "...",
  "Local": "...",
  "Data_inicio": "2026-05-28",
  "Data_final": "2026-05-31",
  "Hora": "18h",
  "Valor": "Gratuito",
  "Link": "https://...",
  "media": "https://..."
}
```

Cria com `origem='painel'`. Útil pra "Ô LidIA, cadastra evento X" via
WhatsApp do bispo. Hoje raramente usado — o painel web cobre 99% dos casos.

---

## 7. Front-end (`/eventos`)

Página standalone em `app/static/eventos.html`. Características:

- **Login compartilhado** com `/disparos` (mesmo `sessionStorage` token).
- **Form único** pra criar/editar — botão muda de "Salvar" pra
  "Atualizar" quando entra em modo edição.
- **Tabela** abaixo, com:
  - Filtro de período (futuros/passados/todos)
  - Filtro de origem (painel/sheets/todos)
  - Chip colorido indicando origem
  - Ações "Editar" e "Excluir" inline
- **Upload de capa**: drag&drop, preview, salva no Drive PAES via proxy n8n.
- **Conflito de planilha**: ao tentar editar/deletar evento `sheets`, mostra
  diálogo de confirmação ("descolar da planilha").
- **Paleta**: dark mode roxo (Twilight Vestry), hue 278°, alinhado ao logo.

---

## 8. Tratamento de eventos passados (estratégia Liriel)

Eventos que já aconteceram ainda têm valor — alguém pode perguntar
*"quando foi o último retiro?"* ou *"teve Cursilho esse ano?"*. Mas eles
**não podem poluir a agenda corrente** nem aparecer espontaneamente
quando alguém pergunta *"tem evento essa semana?"*.

A LidIA adota o mesmo modelo da Liriel (`liriel-agent/app/services/events_service.py`):

### 8.1 Soft-delete via `is_active`

- Coluna `is_active boolean DEFAULT true` em `eventos_paes`
  *(migration pendente — 013)*.
- "Deletar" pelo painel ou pelo `eventos_Lidia` tool vira
  `UPDATE is_active = false`. Nunca `DELETE FROM`.
- Eventos com `is_active = false` **somem das duas listas** (futura e
  histórica). Continuam no banco pra auditoria mas não são lidos por
  nenhum consumidor.

### 8.2 Duas listas, sempre filtradas

| Função | Janela | Pra quê |
|---|---|---|
| `list_future_events(days_ahead=60)` | `data_inicio >= hoje AND data_inicio <= hoje+60d` | Agenda dos próximos 60 dias |
| `list_recent_past_editions(months_back=18, limit=15)` | `data_inicio < hoje AND data_inicio >= hoje-18m`, `DISTINCT ON (nome)` | Última edição de cada nome único, máx 15 |

A função de passado tem o pulo do gato: `DISTINCT ON (nome)`. Se a PAES
tem 5 Cursilhos Masculinos passados, devolve só a edição mais recente.
Limpo.

### 8.3 Injeção dupla no system prompt

Em vez de a LidIA depender da tool `buscar_evento` ser chamada, o
contexto é **sempre injetado** no system prompt a cada conversa:

```
<CONTEXTO_EVENTOS>
{events_context}          ← futuros, formato bullet "- Nome: DD/MM, hora, local"
</CONTEXTO_EVENTOS>

<EVENTOS_PASSADOS>
Últimas edições de eventos que já aconteceram (use APENAS quando a
pessoa perguntar sobre uma edição passada — "quando foi o último retiro?",
"quando teve a última conferência?". NÃO mencione espontaneamente):
{past_events_context}     ← passados, formato "- Nome: última edição em DD/MM/YYYY"
</EVENTOS_PASSADOS>
```

A regra "NÃO mencione espontaneamente" é literal no prompt — o LLM
aprende a só puxar passado quando a pergunta é retrospectiva.

### 8.4 Tool `buscar_evento` ajustada

Continua existindo pra busca por filtros específicos (data, nome
aproximado), mas:

- Default: filtra `data_inicio >= hoje AND is_active = true`.
- Param novo `incluir_passados: bool = false` — quando `true`, a tool
  chama `list_recent_past_editions` em vez do SELECT padrão.
- O LLM seta `incluir_passados=true` automaticamente quando detecta
  intenção retrospectiva ("foi", "aconteceu", "última vez").

### 8.5 Busca semântica (`pgvector`)

Como já temos pgvector na LidIA pra RAG, vai ser reusado:

- Coluna `embedding vector(1536)` em `eventos_paes` (migration 013).
- Embedding gerado a partir de `nome + descricao` no INSERT/UPDATE.
- `search_events(query)` faz híbrido: ordena por `embedding <=> :query_emb`
  com threshold `> 0.25`, fallback `ILIKE` se semântica não retornar.
- Resolve fuzzy match — "retiro dos jovem" → "Retiro de Jovens",
  "aquele acampamento" → match pelo embedding.

### 8.6 Resumo do contrato de comportamento

| Pergunta do usuário | O que a LidIA usa |
|---|---|
| "tem evento essa semana?" | `events_context` (futuros) |
| "que dia tem Cursilho?" | `events_context` (filtrado por nome no LLM) |
| "quando foi o último retiro?" | `past_events_context` |
| "ainda dá pra me inscrever no Happening?" | `events_context` (futuros — se passou, ela responde "já aconteceu, a próxima edição ainda não tem data") |
| "tem evento amanhã?" | `events_context` filtrado pela data |

---

## 9. Resumo das decisões de design

| Decisão | Por quê |
|---|---|
| 3 fontes coexistindo (sheets, painel, gerador) | Migração suave — equipe antiga continua no Sheets, equipe nova no painel, cultos rolam sozinhos |
| `hora` como texto livre | Planilha tinha dados heterogêneos; perderia ~30% num cast pra `TIME` |
| `sheets_row_id` único | Idempotência do sync e do gerador |
| `origem` em check constraint | Garante que UI/tools saibam exatamente de onde veio |
| 409 ao editar/deletar `sheets` sem confirmar | Evita que o usuário do painel sobrescreva mudanças vindas da planilha sem perceber |
| Worker que gera cultos dominicais | Eles são fixos e previsíveis — não faz sentido digitar |
| Soft-delete via `is_active` | Eventos cancelados somem da agenda mas continuam pra auditoria |
| Contexto injetado no prompt (não só via tool) | LidIA responde sobre agenda mesmo sem o LLM lembrar de chamar tool |
| `DISTINCT ON (nome)` no histórico | Evita repetir 5 edições do mesmo evento — só a última |
| Regra "NÃO mencione espontaneamente" no prompt | Passados ficam disponíveis mas só puxados em pergunta retrospectiva |
| Embeddings em `eventos_paes` | Match fuzzy de nome aproximado ("retiro dos jovem") |

---

## 10. Métricas atuais (snapshot)

- **Total de eventos cadastrados:** ~224
- **Por origem (estimativa):**
  - `sheets`: ~110 (legado)
  - `gerador`: ~108 (cultos dominicais dos próximos 3 meses)
  - `painel`: ~6 (eventos criados via UI)
- **Tools mais chamadas pela LidIA:** `buscar_evento` (segunda mais usada,
  atrás só de `buscar_documentos`)

---

## 11. Para onde isso vai (Diacon)

> Quando a migração Diacon entrar, `eventos_paes` é **aposentada**.
> Diacon vira fonte única de eventos. Sheets/gerador/painel local somem.
> `buscar_evento` passa a chamar `GET /events/upcoming` na Diacon.
> O painel `/eventos` continua, mas vira CRUD contra a API Diacon
> (`POST /events/*` quando os endpoints estiverem expostos).
