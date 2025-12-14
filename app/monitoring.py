# app/monitoring.py
from __future__ import annotations

import time
from typing import Any, Dict, List

from sqlalchemy import text

from app.core.config import settings
from app.database import SessionLocal


def _check(name: str, ok: bool, detail: str = "", extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    row: Dict[str, Any] = {"name": name, "ok": bool(ok)}
    if detail:
        row["detail"] = detail
    if extra:
        row["extra"] = extra
    return row


def run_selftest(quick: bool = True) -> dict:
    checks: List[Dict[str, Any]] = []

    # --- ENV sanity ---
    checks.append(_check("env:DATABASE_URL", bool(getattr(settings, "DATABASE_URL", None))))
    checks.append(_check("env:BOT_TOKEN", bool(settings.BOT_TOKEN), detail="optional (bot disabled if missing)"))
    checks.append(_check("env:WEBHOOK_URL", bool(settings.WEBHOOK_URL), detail="optional (webhook auto-set if provided)"))

    # --- DB ---
    db_ok = False
    db_err = ""
    t0 = time.time()
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_ok = True
        finally:
            db.close()
    except Exception as e:
        db_err = repr(e)

    checks.append(_check("db:select1", db_ok, detail=db_err, extra={"ms": int((time.time() - t0) * 1000)}))

    # --- Optional deeper checks (non-blocking for quick) ---
    if not quick:
        # BSC RPC (best-effort)
        bsc_ok = True
        bsc_err = "skipped (BSC_RPC_URL missing)"
        if settings.BSC_RPC_URL:
            bsc_ok = False
            bsc_err = ""
            try:
                from web3 import Web3

                w3 = Web3(Web3.HTTPProvider(settings.BSC_RPC_URL, request_kwargs={"timeout": 5}))
                bn = w3.eth.block_number
                bsc_ok = True
                bsc_err = f"block={bn}"
            except Exception as e:
                bsc_err = repr(e)

        checks.append(_check("bsc:rpc", bsc_ok, detail=bsc_err))

    status = "ok" if all(c.get("ok") for c in checks) else "degraded"
    return {"status": status, "checks": checks}
