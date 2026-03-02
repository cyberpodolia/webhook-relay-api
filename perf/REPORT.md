# Performance Report Template

This file is a template for recording measured perf outcomes. Replace placeholders with measured values only.

## Run Metadata
- Date (UTC):
- Executor:
- Branch / Commit:
- Relay mode: host-relay | docker-relay
- k6 version:
- Data sources: Prometheus + InfluxDB

## Environment
- Host CPU / RAM:
- OS:
- Docker version:
- Python version:
- App config overrides used:

## Scenarios Executed
| Scenario | Duration | Target | Status | Notes |
|---|---:|---|---|---|
| sanity |  |  |  |  |
| baseline |  |  |  |  |
| spike |  |  |  |  |
| soak |  |  |  |  |
| slow_receivers |  |  |  |  |
| flaky_receivers |  |  |  |  |
| large_payload |  |  |  |  |

## Max Stable RPS
- Definition used:
- Measured max stable RPS:
- Corresponding latency (p95/p99):
- Error rate at max stable point:

## Failure Mode Taxonomy
| Failure Mode | Trigger Scenario | Symptom | Detection Signal | Mitigation |
|---|---|---|---|---|
| timeout |  |  |  |  |
| downstream 5xx |  |  |  |  |
| relay saturation |  |  |  |  |
| resource pressure |  |  |  |  |

## Recovery / Drain Time
- Queue/backlog indicator used:
- Recovery start timestamp:
- Recovery complete timestamp:
- Drain time:

## Resource Profile (cAdvisor-backed)
- Peak container CPU (service + value):
- Peak container RAM working set (service + value):
- Notes on resource bottlenecks:

## Artifacts
- Grafana screenshots (latency, error rate, relay RPS, CPU, RAM):
- Raw k6 output export location:
- Prometheus snapshot or query export location:

## Conclusions
- Primary bottleneck:
- Safe operating envelope:
- Recommended next perf experiment:
