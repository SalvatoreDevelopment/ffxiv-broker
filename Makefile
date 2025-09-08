PY=poetry run

.PHONY: setup lint typecheck test run docker-up docker-down format precommit

setup:
	poetry install
	pre-commit install

lint:
	$(PY) ruff check .
	$(PY) black --check .
	$(PY) isort --check-only .

typecheck:
	$(PY) mypy .

test:
	$(PY) pytest -q

format:
	$(PY) ruff check --fix .
	$(PY) black .
	$(PY) isort .

run:
	$(PY) uvicorn broker.api.main:app --reload --port 8000

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

