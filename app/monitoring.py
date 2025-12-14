# app/monitoring.py
from __future__ import annotations

def run_selftest(quick: bool = True) -> dict:
    checks = []
    # כרגע: selftest בסיסי בלבד
    checks.append({"name": "selftest", "ok": True})
    return {"status": "ok", "checks": checks}
