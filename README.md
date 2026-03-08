# Webhook Relay API


Small FastAPI webhook intake service with SQLAlchemy persistence, optional outbound relay (`httpx`), Prometheus metrics, and Alembic migrations.

## Features

- Webhook intake with optional HMAC-SHA256 signature verification (`X-Webhook-Signature`)
- Request body size limit and optional source allowlist
- Idempotency by `Idempotency-Key` per source
- Optional outbound relay with SSRF protections and retry/backoff
- Stored relay result metadata on events
- Cursor pagination and source filtering for event listing
- Prometheus metrics (`/metrics`)
- Retention cleanup via admin endpoint and CLI script
- Alembic migrations for DB schema management

## Endpoints

- `GET /health`
- `GET /ready`
- `GET /metrics`
- `POST /webhooks/{source}`
- `GET /events?limit=50&cursor=...&source=...`
- `GET /events/{event_id}`
- `POST /admin/cleanup` (requires `X-Admin-Token`)

## Environment Variables

- `APP_HOST` (default `0.0.0.0`)
- `APP_PORT` (default `8000`)
- `DATABASE_URL` (default `sqlite:///./data/app.db`)
- `TARGET_URL` (optional outbound relay target)
- `LOG_LEVEL` (default `INFO`)
- `WEBHOOK_SECRET` (optional; if set, `X-Webhook-Signature` is required)
- `MAX_BODY_BYTES` (default `1048576`)
- `ALLOWED_SOURCES` (optional comma-separated webhook sources)
- `RELAY_ALLOW_HOSTS` (optional comma-separated hostnames allowed for `TARGET_URL`)
- `EVENT_RETENTION_DAYS` (optional; enables cleanup retention cutoff)
- `ADMIN_TOKEN` (optional; required for `/admin/cleanup` when set)

## Local Development

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

## Quickstart

```bash
curl http://127.0.0.1:8000/health

BODY='{"order_id":123,"status":"paid"}'
SIG=$(python - <<'PY'
import hashlib, hmac
secret=b"change-me"
body=b'{"order_id":123,"status":"paid"}'
print(hmac.new(secret, body, hashlib.sha256).hexdigest())
PY
)

curl -X POST http://127.0.0.1:8000/webhooks/demo \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: $SIG" \
  -H "Idempotency-Key: example-1" \
  -d "$BODY"

curl "http://127.0.0.1:8000/events?limit=10"
```

## Security Notes

- Relay only supports `http`/`https` targets.
- Relay preflight blocks localhost/private/reserved/link-local IPs.
- `RELAY_ALLOW_HOSTS` is recommended in production and can disable relay to unexpected hosts.
- Disallowed sources return `404` to avoid source enumeration.

## Cleanup

Admin endpoint:

```bash
curl -X POST http://127.0.0.1:8000/admin/cleanup -H "X-Admin-Token: $ADMIN_TOKEN"
```

CLI for cron:

```bash
python -m app.scripts.cleanup
```

## Docker

```bash
docker compose up --build
```

Container startup runs `alembic upgrade head` before launching `uvicorn`.

## Checks

```bash
ruff check .
ruff format --check .
pytest
```

## Performance Testing

The production-style perf harness is in `perf/`.

- Runbook: `perf/README.md`
- Compose stack: `perf/docker-compose.perf.yml`
- Modes: host-relay (recommended) and docker-relay (optional profile)

### Perf Artifact Capture

- Report template: `perf/REPORT.md`
- Save Grafana screenshots for latency, error rate, relay RPS, CPU, and RAM, then reference them in `perf/REPORT.md`.
- Record k6 command lines, scenario duration, and relay mode (host-relay or docker-relay) in `perf/REPORT.md`.
- Keep report entries evidence-based; mark unknowns as `UNKNOWN` when prerequisites are missing.

### Quick Host-Relay Run (Windows, 18000)

```powershell
# Terminal A (API)
cd C:\work\repo1-webhook-relay-api
.\.venv\Scripts\activate
$env:TARGET_URL="http://127.0.0.1:18101/ingest"
uvicorn app.main:app --host 0.0.0.0 --port 18000
```

```powershell
# Terminal B (perf)
cd C:\work\repo1-webhook-relay-api\perf
docker compose -f docker-compose.perf.yml up -d --build
.\scripts\run-k6.ps1 -Scenario sanity.js -Target "http://host.docker.internal:18000" -InfluxUrl "http://host.docker.internal:8086/k6"
```

### Latest Measured Results (2026-03-08)

Context:

- Mode: host-relay (API on host, perf stack in Docker)
- Relay enabled to local perf receivers with explicit dev/perf override:
  - `RELAY_ALLOW_PRIVATE_IPS=true`
  - `RELAY_WORKER_CONCURRENCY=2`
  - `RELAY_QUEUE_SIZE=200`

Measured intake latency for `POST /webhooks/perf` (k6):

| Scenario | p95 | p99 | http_req_failed |
|---|---:|---:|---:|
| baseline | 25.72 ms | 60.30 ms | 0.00% |
| slow_receivers | 43.55 ms | 91.29 ms | 0.00% |
| flaky_receivers | 92.06 ms | 142.47 ms | 0.00% |

Notes:

- `http_req_failed` reflects the intake endpoint HTTP result. Downstream relay success/failure is recorded separately (DB `relay_attempted`/`relay_success`/`relay_reason` and Prometheus relay metrics).
- Keep `RELAY_ALLOW_PRIVATE_IPS` disabled by default; it exists to make local perf harness runs possible.
