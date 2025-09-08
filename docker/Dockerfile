# syntax=docker/dockerfile:1

ARG PY_VERSION=3.12

FROM python:${PY_VERSION}-slim AS builder
ENV PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md /app/
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install poetry && \
    POETRY_VIRTUALENVS_CREATE=false poetry install --only=main --no-root

COPY broker /app/broker
RUN /opt/venv/bin/pip install .

FROM python:${PY_VERSION}-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd -ms /bin/bash app
USER app
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app broker /app/broker

EXPOSE 8000
CMD ["uvicorn", "broker.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

