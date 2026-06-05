# Migração Diacon — Status Final

## ✅ Concluído (Fases 1A, 1B, 2, 3, 4)

### Tools que **usam Diacon** como fonte de verdade

| Tool | Endpoint Diacon | Substituiu |
|---|---|---|
| `oracao_do_dia` (novo) | `POST /oracao/link` | — |
| `pedido_oracao` (novo) | `POST /oracao/pedido` | `resposta_oracao` (kept como alias) |
| `link_foto_perfil` (novo) | `POST /members/photo-link` | — |
| `qr_celula` (novo) | `GET /cells/qr` | — |
| `celulas_proximas` (novo) | `GET /cells/near` | — |
| `buscar_evento` | `GET /events/upcoming` + filtros locais | Postgres `eventos_paes` |
| `cadastrar_contato` | `POST /members` (idempotente) | `INSERT contacts` |
| `cadastrar_aniversario` | `PATCH /members` (`birth_date`) | `UPDATE contacts.aniversario` |
| `atualizar_sobrenome` | `PATCH /members` (`full_name`) | `UPDATE contacts.full_name` |
| `novos_convertidos` | `POST /pastoral` `area=decision` | `INSERT novos_convertidos` |
| `notificar_time_interno` | `POST /pastoral` + mapa equipe→area | Sheets (fallback mantido) |

### Workers adaptados

| Worker | Mudança |
|---|---|
| `aniversarios` (8h BR diário) | `GET /birthdays?range=today` com fallback Postgres |

### Migração de dados

- **619 contatos** subidos para a Diacon via `POST /members`:
  - 588 já existiam (Diacon retorna `created=false`)
  - 1 criado novo
  - 29 telefones rejeitados (formato inválido — DDI estrangeiro, lixo)
  - 1 sem telefone (pulado)

## 🗃️ Tabelas Postgres — status

| Tabela | Status | Razão |
|---|---|---|
| `contacts` | **mantida (write-behind)** | Debounce, dedup local, painel `/disparos` |
| `eventos_paes` | **mantida (legado)** | Painel `/eventos` ainda escreve nela; sheets_sync ainda popula |
| `novos_convertidos` | **mantida (write-behind)** | Cache local; Diacon é fonte |
| `liderancas` | mantida | Não migrada (n8n usa) |
| `pastores_aniversario` | mantida | Worker `aniversarios` fallback |
| `equipes_responsaveis` | mantida | Mapa interno + Sheets fallback |
| `messages`, `knowledge_chunks`, `plano_de_leitura`, `disparos*`, `llm_analytics`, `usuarios_painel` | mantidas | Não fazem parte da Diacon |

## 📋 Próximos passos (não bloqueantes)

1. **Aposentar `eventos_paes`** quando a Diacon expuser endpoints de escrita
   (POST/PATCH/DELETE de eventos) — hoje só temos read.
2. **Reescrever painel `/eventos`** pra falar com Diacon (POST/PATCH).
3. **Desligar `sheets_sync` de eventos** quando todos saírem da planilha.
4. **Deletar tabela `equipes_responsaveis`** depois que todos os fluxos
   estiverem confiando no `area` da Diacon (mapa hoje vive no código).

## 🔧 Configuração

Env vars:
```
DIACON_BASE_URL=https://diacon.ia.br/api/v1/paes-catedral
DIACON_TOKEN=dia_***
DIACON_TIMEOUT_SECONDS=30
```

Cliente: `app/services/diacon_client.py` (httpx + retry tenacity).
