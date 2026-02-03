import importlib

from fastapi.testclient import TestClient


def make_client(tmp_path, monkeypatch, target_url=""):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("TARGET_URL", target_url)
    monkeypatch.setenv("LOG_LEVEL", "ERROR")

    import app.core.config as config

    config.get_settings.cache_clear()
    import app.main as main

    importlib.reload(main)
    return TestClient(main.app)


def test_health_ok(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_event_stores_and_returns_event_id(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    payload = {"a": 1}
    resp = client.post("/webhooks/source1", json=payload)
    assert resp.status_code == 200
    assert "event_id" in resp.json()


def test_invalid_payload_returns_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/webhooks/source1", json=[1, 2, 3])
    assert resp.status_code == 422


def test_list_events_returns_created_event(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    payload = {"a": 1}
    resp = client.post("/webhooks/source1", json=payload)
    event_id = resp.json()["event_id"]

    resp_list = client.get("/events")
    assert resp_list.status_code == 200
    events = resp_list.json()["events"]
    assert any(e["event_id"] == event_id for e in events)


def test_relay_is_called_when_target_url_set(tmp_path, monkeypatch):
    called = {"value": False}

    async def fake_relay_event(event, target_url, request_id):
        called["value"] = True
        return {"attempted": True, "success": True, "status_code": 200}

    import app.services.relay as relay

    monkeypatch.setattr(relay, "relay_event", fake_relay_event)
    client = make_client(tmp_path, monkeypatch, target_url="https://example.com/endpoint")

    resp = client.post("/webhooks/source1", json={"a": 1})
    assert resp.status_code == 200
    assert called["value"] is True
