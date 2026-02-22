"""API tests covering security controls, relay behavior, and pagination semantics."""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient


def _reload_app(monkeypatch, tmp_path, **env):
    """Reload the app module after env changes so cached settings are refreshed."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("TARGET_URL", env.pop("TARGET_URL", ""))
    monkeypatch.setenv("LOG_LEVEL", "ERROR")

    defaults = {
        "WEBHOOK_SECRET": "",
        "MAX_BODY_BYTES": "1048576",
        "ALLOWED_SOURCES": "",
        "RELAY_ALLOW_HOSTS": "",
        "EVENT_RETENTION_DAYS": "",
        "ADMIN_TOKEN": "",
    }
    defaults.update({k: str(v) for k, v in env.items()})
    for key, value in defaults.items():
        monkeypatch.setenv(key, value)

    import app.core.config as config

    config.get_settings.cache_clear()
    import app.main as main

    importlib.reload(main)
    return main


@contextmanager
def make_client(tmp_path, monkeypatch, **env):
    """Create a TestClient with isolated SQLite DB and env configuration."""
    main = _reload_app(monkeypatch, tmp_path, **env)
    with TestClient(main.app) as client:
        yield client


def _sign(secret: str, body: bytes) -> str:
    """Match the production HMAC scheme for request-signature test cases."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_health_ok(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_create_event_stores_and_returns_event_id(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch) as client:
        resp = client.post("/webhooks/source1", json={"a": 1})
        assert resp.status_code == 200
        body = resp.json()
        assert "event_id" in body
        assert body["received_at"].endswith("+00:00") or body["received_at"].endswith("Z")


def test_invalid_payload_returns_422(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch) as client:
        resp = client.post("/webhooks/source1", json=[1, 2, 3])
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] in {
            "payload_must_be_a_json_object",
        }


def test_signature_required_and_invalid_signature(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch, WEBHOOK_SECRET="topsecret") as client:
        resp_missing = client.post("/webhooks/source1", json={"a": 1})
        assert resp_missing.status_code == 401

        body = json.dumps({"a": 1}).encode("utf-8")
        resp_bad = client.post(
            "/webhooks/source1",
            content=body,
            headers={"Content-Type": "application/json", "X-Webhook-Signature": "bad"},
        )
        assert resp_bad.status_code == 401

        resp_ok = client.post(
            "/webhooks/source1",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": _sign("topsecret", body),
            },
        )
        assert resp_ok.status_code == 200


def test_size_limit_413(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch, MAX_BODY_BYTES=10) as client:
        resp = client.post(
            "/webhooks/source1",
            content=b'{"1234567890":1}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 413


def test_allowed_sources_gating_returns_404(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch, ALLOWED_SOURCES="source1,source2") as client:
        resp = client.post("/webhooks/blocked", json={"a": 1})
        assert resp.status_code == 404


def test_idempotency_replay_returns_same_event(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch) as client:
        headers = {"Idempotency-Key": "abc-123"}
        first = client.post("/webhooks/source1", json={"a": 1}, headers=headers)
        # Edge case: different payload should still replay the original event when
        # the source + idempotency key matches.
        second = client.post("/webhooks/source1", json={"a": 999}, headers=headers)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["event_id"] == second.json()["event_id"]
        assert first.json()["received_at"] == second.json()["received_at"]

        events = client.get("/events").json()["events"]
        assert len(events) == 1


def test_ssrf_blocking_private_ip_prevents_relay(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch, TARGET_URL="http://127.0.0.1:9999/webhook") as client:
        resp = client.post("/webhooks/source1", json={"a": 1})
        assert resp.status_code == 200
        relay = resp.json()["relay"]
        assert relay["attempted"] is False
        assert relay["reason"] == "blocked_ip"


def test_allowlist_host_permits_relay_with_mock_target(tmp_path, monkeypatch):
    import app.services.relay as relay

    async def fake_resolve(host: str):
        # Why: bypass real DNS/network so the test remains hermetic and fast.
        return {"93.184.216.34"}

    async def fake_post(self, url, json, headers):  # noqa: A002
        # Why: patch AsyncClient.post directly instead of spinning up a test server.
        class Resp:
            status_code = 204

        return Resp()

    monkeypatch.setattr(relay, "_resolve_ips_for_host", fake_resolve)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    with make_client(
        tmp_path,
        monkeypatch,
        TARGET_URL="https://example.com/endpoint",
        RELAY_ALLOW_HOSTS="example.com",
    ) as client:
        resp = client.post("/webhooks/source1", json={"a": 1})
        assert resp.status_code == 200
        relay_data = resp.json()["relay"]
        assert relay_data["attempted"] is True
        assert relay_data["success"] is True
        assert relay_data["status_code"] == 204


def test_pagination_cursor_correctness_and_filtering(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch) as client:
        created = []
        for source in ["s1", "s1", "s2"]:
            resp = client.post(f"/webhooks/{source}", json={"source": source})
            created.append(resp.json()["event_id"])

        page1 = client.get("/events", params={"limit": 2})
        assert page1.status_code == 200
        body1 = page1.json()
        assert len(body1["events"]) == 2
        assert body1["next_cursor"]

        page2 = client.get("/events", params={"limit": 2, "cursor": body1["next_cursor"]})
        assert page2.status_code == 200
        body2 = page2.json()
        # Invariant: pages should not overlap when advancing via `next_cursor`.
        ids1 = {e["event_id"] for e in body1["events"]}
        ids2 = {e["event_id"] for e in body2["events"]}
        assert ids1.isdisjoint(ids2)

        filtered = client.get("/events", params={"source": "s2"})
        assert filtered.status_code == 200
        assert all(e["source"] == "s2" for e in filtered.json()["events"])


def test_cleanup_deletes_old_events_with_admin_token(tmp_path, monkeypatch):
    main = _reload_app(
        monkeypatch,
        tmp_path,
        EVENT_RETENTION_DAYS=7,
        ADMIN_TOKEN="admintoken",
    )
    from app.db.models import Event
    from app.db.session import get_db

    old_ts = datetime.now(timezone.utc) - timedelta(days=30)
    new_ts = datetime.now(timezone.utc)
    # Why: seed rows directly to control timestamps without sleeping or monkeypatching time.
    with get_db() as db:
        db.add(
            Event(
                id="00000000-0000-0000-0000-000000000001",
                source="s1",
                received_at=old_ts,
                payload={"old": True},
                headers={},
                request_id="00000000-0000-0000-0000-000000000001",
            )
        )
        db.add(
            Event(
                id="00000000-0000-0000-0000-000000000002",
                source="s1",
                received_at=new_ts,
                payload={"old": False},
                headers={},
                request_id="00000000-0000-0000-0000-000000000002",
            )
        )

    with TestClient(main.app) as client:
        unauthorized = client.post("/admin/cleanup")
        assert unauthorized.status_code == 401

        resp = client.post("/admin/cleanup", headers={"X-Admin-Token": "admintoken"})
        assert resp.status_code == 200
        assert resp.json()["deleted_count"] == 1

        events = client.get("/events").json()["events"]
        assert len(events) == 1
        assert events[0]["payload"] == {"old": False}


def test_metrics_endpoint_present(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch) as client:
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "http_requests_total" in resp.text
