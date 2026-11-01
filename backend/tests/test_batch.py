"""Batch sweep API: run several scenarios headlessly and compare them."""
import time

import pytest
from fastapi.testclient import TestClient

from app.core.scenarios import SCENARIOS, default_config_for, default_route_for
from app.main import app
from app.services.batch_service import MAX_RUNS


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _wait(client, timeout_s=90):
    """Poll /batch/status until the sweep leaves the running state."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        st = client.get("/api/batch/status").json()
        if st["state"] != "running":
            return st
        time.sleep(0.5)
    raise AssertionError("batch did not finish in time")


def test_catalogue_covers_five_scenarios():
    kinds = [s.id.value for s in SCENARIOS]
    assert len(kinds) == 5
    assert set(kinds) == {"normal", "outage", "drift", "spoofing", "complex"}


def test_complex_uses_random_route_and_outage():
    cfg = default_config_for("complex")
    assert cfg.scenario.value == "outage"          # complex embeds a mid-run outage
    assert default_route_for("complex") == "random"
    assert default_route_for("outage") == "road"


def test_sweep_scores_every_scenario(client):
    plan = {
        "scenarios": ["normal", "outage", "drift", "spoofing", "complex"],
        # long enough to pass every fault onset (spoofing starts at t=18 s),
        # otherwise the run would end before the fault is injected
        "durations_s": [30],
        "seeds": [42],
        "rate_hz": 10,
    }
    first = client.post("/api/batch/run", json=plan).json()
    assert first["state"] in ("running", "completed")
    st = _wait(client)
    assert st["state"] == "completed"
    assert st["completed"] == 5 and st["total"] == 5

    by_kind = st["byKind"]
    assert set(by_kind) == set(plan["scenarios"])
    for kind, row in by_kind.items():
        assert row["runs"] == 1
        # every scenario is scored by the same estimators
        for algo in ("gnss", "ekf", "rts_smoothed", "dead_reckoning"):
            assert algo in row["estimators"], (kind, algo)
            assert row["estimators"][algo]["rmse_m"] >= 0
    # spoofing is the worst case for raw GNSS, and the EKF must beat it
    assert by_kind["spoofing"]["estimators"]["gnss"]["rmse_m"] > by_kind["normal"]["estimators"]["gnss"]["rmse_m"]
    assert by_kind["spoofing"]["ekf_vs_gnss_pct"] > 50


def test_seeds_aggregate_with_spread(client):
    plan = {"scenarios": ["outage"], "durations_s": [10], "seeds": [1, 2], "rate_hz": 10}
    client.post("/api/batch/run", json=plan)
    st = _wait(client)
    assert st["state"] == "completed"
    row = st["byKind"]["outage"]
    assert row["runs"] == 2 and row["seeds"] == [1, 2]
    assert row["estimators"]["ekf"]["rmse_std_m"] is not None


def test_rejects_empty_scenario_list(client):
    r = client.post("/api/batch/run", json={"scenarios": [], "seeds": [1]})
    assert r.status_code == 422


def test_rejects_oversized_plan(client):
    seeds = list(range(1, 12))
    r = client.post(
        "/api/batch/run",
        json={"scenarios": ["normal", "outage", "drift", "spoofing", "complex"], "seeds": seeds},
    )
    assert r.status_code == 422
    assert str(MAX_RUNS) in r.json()["detail"]


def test_busy_batch_is_conflict(client):
    plan = {"scenarios": ["normal", "outage", "drift"], "durations_s": [25], "seeds": [3]}
    client.post("/api/batch/run", json=plan)
    second = client.post("/api/batch/run", json={"scenarios": ["normal"], "durations_s": [5]})
    assert second.status_code in (409, 200)   # 200 only if the first finished instantly
    _wait(client)


def test_cancel_stops_the_sweep(client):
    plan = {"scenarios": ["normal", "outage", "drift", "spoofing"], "durations_s": [60], "seeds": [9]}
    client.post("/api/batch/run", json=plan)
    time.sleep(0.4)
    assert client.post("/api/batch/cancel").json()["state"] == "cancelled"
    st = _wait(client)
    assert st["state"] == "cancelled"
    assert st["completed"] < st["total"]
