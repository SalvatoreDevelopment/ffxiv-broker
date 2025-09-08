# FFXIV Market Advisor (ffxiv-broker)

Backend FastAPI per analisi del mercato FFXIV usando Universalis e XIVAPI.

## Requisiti
- Python 3.11+
- Poetry
- Docker (per esecuzione con Redis)

## Avvio rapido

```powershell
# Verifica Poetry
poetry --version

# Clona/inizializza repo
git init ffxiv-broker
cd ffxiv-broker

# Installa dipendenze
poetry install

# Crea file .env
copy .env.example .env

# Lancia Redis + API con Docker Compose
docker compose up -d

# Lint, type e test
poetry run ruff check .
poetry run black --check .
poetry run mypy .
poetry run pytest -q

# Avvia server dev
poetry run uvicorn broker.api.main:app --reload --port 8000
```

## Configurazione
Variabili in `.env` (vedi `.env.example`):
- `REDIS_URL`
- `UNIVERSALIS_BASE`
- `XIVAPI_BASE`
- `CACHE_TTL_SHORT`, `CACHE_TTL_LONG`
- `USER_AGENT`, `REQUESTS_RPS`, `RETRY_MAX`
- `LOG_LEVEL`

## Struttura
Vedi albero cartelle nella richiesta. Questo repo contiene:
- API FastAPI con rotte `/healthz`, `/item/{id}` (base), `/craft/{id}` (bozza), `/advice` (bozza)
- Client async per Universalis/XIVAPI (con cache Redis)
- Servizi metriche e craft (bozze funzionanti minime)
- Export Excel (bozza)
- Docker multi-stage e docker-compose (API + Redis)
- CI GitHub Actions per lint/type/test/build

## Note
- Alcune parti sono marcate TODO (ricette nested da XIVAPI/Garland, vendor prices, ranking avanzato). 
- Endpoint minimi sono operativi; estensioni suggerite nei sub-prompt.

## Licenza
MIT

