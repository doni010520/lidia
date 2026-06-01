# n8n Workflows da LidIA

## lidia-google-proxy

Webhook que serve como gateway para Google Sheets, Drive e Gmail —
permite que o backend Python rode sem service account local.

### Import no n8n

1. **Workflows → Import from File** → escolher `lidia_google_proxy.json`
2. Conectar credenciais Google nos nodes:
   - Sheets Read / Append / Read Cell / Update → **Google Sheets OAuth2**
   - Drive Search / List / Download → **Google Drive OAuth2**
   - Gmail Send → **Gmail OAuth2**
   (pode reusar as credenciais que já estão nos outros workflows PAES)
3. Definir env var no n8n: `LIDIA_PROXY_TOKEN` = `<segredo forte, ex: 32 bytes random>`
4. **Ativar** o workflow
5. Copiar a URL de produção do webhook (algo como `https://n8n.../webhook/lidia-google`)

### Configurar no app (EasyPanel → lidia-app → Env)

```
N8N_GOOGLE_WEBHOOK_URL=https://webhook.dev.beniteklab.shop/webhook/lidia-google
N8N_GOOGLE_TOKEN=<mesmo valor do LIDIA_PROXY_TOKEN>
```

Quando essas duas variáveis estiverem setadas, **todos** os clients
(`app/services/sheets_client.py`, `drive_client.py`, `gmail_client.py`)
passam a usar o proxy automaticamente.

### Contrato HTTP

```
POST {N8N_GOOGLE_WEBHOOK_URL}
Header: X-Lidia-Token: <token>
Body: {"action": "<verbo>", "params": {...}}

Resposta: {"ok": true, "data": <resultado>}
   ou:    {"ok": false, "error": "..."}
```

### Actions

| Action | Params | Retorno |
|---|---|---|
| `sheets.read` | `sheet_id, range` | `list[list[str]]` |
| `sheets.append` | `sheet_id, range, values` | `{updatedRows}` |
| `sheets.read_cell` | `sheet_id, range` | `str` |
| `sheets.update` | `sheet_id, range, value` | `{}` |
| `drive.search` | `query, folder_id?, max_results` | `list[file]` |
| `drive.list` | `folder_id, max_results` | `list[file]` |
| `drive.download` | `file_id` | `{content_b64, mimetype, name}` |
| `gmail.send` | `to, subject, body, from?` | `{id}` |
