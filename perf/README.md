# Performance Harness

This folder contains the Docker-based load-testing and observability stack for Webhook Relay API.

## Modes

1. host-relay (recommended)
- Run the API on the host machine (`uvicorn app.main:app --host 0.0.0.0 --port 18000`).
- Containers use `host.docker.internal:18000` to scrape relay metrics and to drive k6 traffic.
- This avoids rebuilding the API image for every local code change.

2. docker-relay (optional)
- Enable the `relay` service with compose profile `docker-relay`.
- Use when you need all components to run inside Docker.
- Relay metrics target becomes `relay:8000` inside the compose network.

## Stack Components

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (default `admin/admin`)
- InfluxDB 1.8 (k6 output): `http://localhost:8086`
- cAdvisor: `http://localhost:8088`
- Receiver fast: `http://localhost:18101/ingest`
- Receiver slow: `http://localhost:18102/ingest`
- Receiver flaky: `http://localhost:18103/ingest`

## Bring Up Stack

```bash
docker compose -f perf/docker-compose.perf.yml up -d --build
```

To include the optional docker-relay service:

```bash
docker compose -f perf/docker-compose.perf.yml --profile docker-relay up -d --build
```

## k6 Target Endpoints

- Host-relay target from k6 container: `http://host.docker.internal:18000`
- Docker-relay target from k6 container: `http://relay:8000`
- Suggested webhook path: `/webhooks/perf`

## Prometheus Scrape Targets

Configured in `perf/prometheus/prometheus.yml`:
- host relay metrics: `host.docker.internal:18000/metrics`
- docker relay metrics: `relay:8000/metrics`
- receivers: `receiver-fast:8080`, `receiver-slow:8080`, `receiver-flaky:8080`
- cAdvisor: `cadvisor:8080`

## Run k6 Scenario (Windows)

```powershell
cd perf
.\scripts\run-k6.ps1 -Scenario baseline.js -Target "http://host.docker.internal:18000" -InfluxUrl "http://host.docker.internal:8086/k6"
```

Scenarios are placed in `perf/k6/scenarios/`.

## Verified Windows Commands (host-relay on 18000)

Terminal A (API):

```powershell
cd C:\work\repo1-webhook-relay-api
.\.venv\Scripts\activate
$env:TARGET_URL="http://127.0.0.1:18101/ingest"
uvicorn app.main:app --host 0.0.0.0 --port 18000
```

Terminal B (perf stack + k6):

```powershell
cd C:\work\repo1-webhook-relay-api\perf
docker compose -f docker-compose.perf.yml up -d --build
.\scripts\run-k6.ps1 -Scenario sanity.js -Target "http://host.docker.internal:18000" -InfluxUrl "http://host.docker.internal:8086/k6"
.\scripts\run-k6.ps1 -Scenario baseline.js -Target "http://host.docker.internal:18000" -InfluxUrl "http://host.docker.internal:8086/k6"
.\scripts\run-k6.ps1 -Scenario spike.js -Target "http://host.docker.internal:18000" -InfluxUrl "http://host.docker.internal:8086/k6"
```
