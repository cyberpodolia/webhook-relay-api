"""Prometheus metric definitions shared across request and relay code paths."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)

# Rationale: source label is expected to be low-cardinality and controlled by
# webhook route naming/allowlists, unlike payload-derived labels.
EVENTS_RECEIVED_TOTAL = Counter(
    "webhook_events_received_total",
    "Webhook events received",
    ["source"],
)

RELAY_ATTEMPTS_TOTAL = Counter(
    "webhook_relay_attempts_total",
    "Outbound relay attempts",
)

RELAY_SUCCESSES_TOTAL = Counter(
    "webhook_relay_successes_total",
    "Successful outbound relays",
)

RELAY_LATENCY_SECONDS = Histogram(
    "webhook_relay_latency_seconds",
    "Outbound relay request latency",
)
