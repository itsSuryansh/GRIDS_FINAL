"""REST + WebSocket API tests using FastAPI's TestClient (no live server)."""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


FAST_CONFIG = {
    "scenario": {
        "scenario": "outage",
        "outage_start_s": 1.0,
        "outage_duration_s": 1.0,
        "drift_onset_s": 1.0,
        "drift_rate_ms": 0.6,
        "drift_max_m": 100.0,
        "spoof_onset_s": 1.0,
        "spoof_jump_m": 60.0,
        "spoof_drift_ms": 0.8,
        "spoof_heading_bias_deg": 25.0,
    },
    "duration_s": 4.0,
    "rate_hz": 20.0,
    "speed_ms": 12.0,
    "route_pattern": "curved",
    "origin_lat": 26.9124,
    "origin_lon": 75.7873,
    "initial_heading_deg": 30.0,
}


def wait_for_state(client, target, timeout=30.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get("/api/simulation/status").json()
        if st["state"] == target:
            return st
        time.sleep(0.1)
    raise AssertionError(f"simulation never reached state {target}")


def test_health_and_info(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"

    info = client.get("/api/system/info").json()
    assert info["data_source"] == "SIMULATED"
    assert "does not establish real-world performance" in info["disclaimer"]


def test_scenarios_and_patterns(client):
    r = client.get("/api/simulation/scenarios")
    assert r.status_code == 200
    ids = {s["id"] for s in r.json()}
    assert ids == {"normal", "outage", "drift", "spoofing", "complex"}
    for s in r.json():
        assert s["description"] and s["expected"]

    p = client.get("/api/simulation/patterns").json()
    assert "curved" in p["patterns"]


def test_validation_rejects_bad_config(client):
    bad = dict(FAST_CONFIG)
    bad["duration_s"] = -5
    assert client.post("/api/simulation/start", json=bad).status_code == 422

    bad2 = dict(FAST_CONFIG)
    bad2["route_pattern"] = "custom"     # custom requires waypoints
    assert client.post("/api/simulation/start", json=bad2).status_code == 422

    bad3 = dict(FAST_CONFIG)
    bad3["scenario"] = {"scenario": "outage", "outage_duration_s": 0}
    assert client.post("/api/simulation/start", json=bad3).status_code == 422


def test_full_lifecycle(client):
    client.post("/api/simulation/reset")
    r = client.post("/api/simulation/start", json=FAST_CONFIG)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["run_id"]
    session_id = body["session_id"]
    assert session_id is not None

    wait_for_state(client, "running")
    time.sleep(0.5)

    cur = client.get("/api/navigation/current").json()
    assert cur["available"] is True
    frame = cur["frame"]
    for key in ("truth_lat", "ekf_lat", "dr_lat", "speed_ms", "heading_deg", "uncertainty_m"):
        assert key in frame

    hist = client.get("/api/navigation/history?limit=50").json()
    assert hist["count"] > 0 and len(hist["samples"]) == hist["count"]

    route = client.get("/api/navigation/route").json()
    assert len(route["route"]) > 2

    # pause / resume
    assert client.post("/api/simulation/pause").status_code == 200
    st = client.get("/api/simulation/status").json()
    assert st["state"] == "paused"
    step_at_pause = st["step"]
    time.sleep(0.6)
    assert client.get("/api/simulation/status").json()["step"] == step_at_pause
    assert client.post("/api/simulation/resume").status_code == 200

    # stop
    assert client.post("/api/simulation/stop").status_code == 200
    st = client.get("/api/simulation/status").json()
    assert st["state"] in ("stopped", "completed")

    # analytics after the run
    cmp = client.get("/api/analytics/compare").json()
    assert cmp["session_id"] == session_id
    assert set(cmp["algorithms"]) == {"gnss", "dead_reckoning", "ekf", "ekf_ml"}
    assert cmp["algorithms"]["ekf"]["samples"] > 0
    assert cmp["series"]

    summary = client.get("/api/analytics/summary").json()
    assert summary["available"]

    # stored session retrieval
    sessions = client.get("/api/analytics/sessions").json()
    assert any(s["id"] == session_id for s in sessions["sessions"])
    detail = client.get(f"/api/analytics/sessions/{session_id}").json()
    assert detail["sample_count"] > 0
    assert detail["metrics"]["ekf"]["rmse_m"] >= 0.0
    assert client.get("/api/analytics/sessions/999999").status_code == 404

    # reset clears the run
    assert client.post("/api/simulation/reset").status_code == 200
    assert client.get("/api/navigation/current").json()["available"] is False


def test_completed_run_reports_metrics(client):
    client.post("/api/simulation/reset")
    client.post("/api/simulation/start", json={**FAST_CONFIG, "duration_s": 2.0})
    st = wait_for_state(client, "completed", timeout=40)
    assert st["progress"] == pytest.approx(1.0, abs=0.15)
    cmp = client.get("/api/analytics/compare").json()
    assert cmp["notes"] and "simulation results" in cmp["notes"][-1]


def test_conflicting_commands_are_rejected(client):
    client.post("/api/simulation/reset")
    # nothing is running
    assert client.post("/api/simulation/pause").status_code == 409
    assert client.post("/api/simulation/resume").status_code == 409
    # stop/reset are always safe
    assert client.post("/api/simulation/stop").status_code == 200
    assert client.post("/api/simulation/reset").status_code == 200


def test_history_empty_without_run(client):
    client.post("/api/simulation/reset")
    h = client.get("/api/navigation/history").json()
    assert h["count"] == 0 and h["samples"] == []


def test_websocket_stream(client):
    client.post("/api/simulation/reset")
    with client.websocket_connect("/api/ws/simulation") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        client.post("/api/simulation/start", json={**FAST_CONFIG, "duration_s": 3.0})
        updates = 0
        while updates < 3:
            msg = ws.receive_json()
            if msg["type"] == "navigation_update":
                updates += 1
                assert "ekf_lat" in msg["data"]
                assert msg["status"]["state"] == "running"
        client.post("/api/simulation/stop")
    st = client.get("/api/simulation/status").json()
    assert st["state"] in ("stopped", "completed")


def test_ws_status_endpoint(client):
    r = client.get("/api/ws/status")
    assert r.status_code == 200
    assert "connected_clients" in r.json()
