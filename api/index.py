"""Vercel Python entrypoint (Option B in docs/DEPLOYMENT.md).

Vercel looks for a module-level `app`; the real application lives in backend/.
The simulation is stateful, so a serverless deployment is only suitable for
short demo runs -- see docs/DEPLOYMENT.md for the recommended split.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.main import app  # noqa: E402,F401
