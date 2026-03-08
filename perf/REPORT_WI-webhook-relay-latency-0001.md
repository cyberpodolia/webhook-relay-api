# WI-webhook-relay-latency-0001 Perf Evidence

## Run Metadata
- Date: 2026-03-08
- Branch: `agent/WI-webhook-relay-perf-0001`
- Scope: `step 00010` baseline perf gate

## Commands Executed
- `docker compose -f perf/docker-compose.perf.yml up -d --build`
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-k6.ps1 -Scenario sanity.js -Target "http://host.docker.internal:18000" -InfluxUrl "http://host.docker.internal:8086/k6"`
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-k6.ps1 -Scenario baseline.js -Target "http://host.docker.internal:18000" -InfluxUrl "http://host.docker.internal:8086/k6"`

## k6 Console Summary
- `sanity`: `http_req_duration p95=17.3ms`, `http_req_failed=0.00%`
- `baseline`: `http_req_duration p95=343.53ms`, `http_req_failed=0.00%`

## Influx Verification (baseline run window)
Window: `2026-03-08T10:42:00Z` to `2026-03-08T10:47:30Z`
- `http_req_duration p95`: `342.87587 ms`
- `http_req_duration p99`: `498.875949 ms`
- `http_req_failed rate`: `0`

## DB Verification (same window)
Table: `events`, filter: `source='perf'`
- `n=3214`
- `relay_attempted sum=0`
- `relay_reason='blocked_ip' count=3214`

## Gate Result for step 00010
- `p95 < 350ms`: PASS
- `p99 < 800ms`: PASS
- `http_req_failed < 0.01`: PASS

## Important Note
This baseline gate pass was measured with relay preflight blocked by SSRF policy (`blocked_ip`), so downstream relay latency was not exercised in this run.
