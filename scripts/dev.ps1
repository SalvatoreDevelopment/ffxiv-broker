Param(
    [switch]$NoDocker
)

poetry install
if (-not $NoDocker) {
    docker compose up -d
}
poetry run uvicorn broker.api.main:app --reload --port 8000

