# GRIDS backend tests

Run from `backend/`:

```bash
python -m pytest -q                    # everything
python -m pytest tests/test_ekf.py -v  # one module
python -m pytest -k scenario -v        # by keyword
```

Tests use a temporary SQLite database (`tests/conftest.py` sets
`GRIDS_DATABASE_URL` before the app is imported) and deterministic random seeds,
so results are repeatable. Scenario tests assert *relative* behaviour (EKF beats
raw GNSS on a normal run, navigation continues through an outage, spoofed fixes
are rejected) rather than absolute accuracy figures, which depend on the
configured noise levels.
