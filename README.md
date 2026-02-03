# Webhook Relay API

[![CI](https://github.com/yourname/repo1-webhook-relay-api/actions/workflows/ci.yml/badge.svg)](https://github.com/yourname/repo1-webhook-relay-api/actions/workflows/ci.yml)

A small FastAPI service that accepts webhooks, normalizes events, stores them, and optionally relays them to a target URL.

## Run in 60 seconds

```bash
python -m venv .venv
. .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

## Quickstart

```bash
curl -X GET http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/webhooks/demo \
  -H "Content-Type: application/json" \
  -d '{"order_id": 123, "status": "paid"}'

curl -X GET "http://127.0.0.1:8000/events?limit=10"
```

## What this demonstrates

- FastAPI service design with structured logging and request IDs
- Webhook normalization and storage using SQLAlchemy
- Optional outbound relay with retries
- Tests with pytest
- Dockerized local run and CI checks

## Configuration

- `APP_HOST` (default `0.0.0.0`)
- `APP_PORT` (default `8000`)
- `DATABASE_URL` (default `sqlite:///./data/app.db`)
- `TARGET_URL` (default empty)
- `LOG_LEVEL` (default `INFO`)

## Metrics

- Prometheus metrics available at `/metrics`

## Local development

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

## Docker

```bash
docker compose up --build
```

## Endpoints

- `GET /health`
- `GET /ready`
- `GET /metrics`
- `POST /webhooks/{source}`
- `GET /events?limit=50`
- `GET /events/{event_id}`
