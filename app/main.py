# app/main.py
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.database import init_db
from app.bot.investor_wallet_bot import initialize_bot, process_webhook
from app.monitoring import run_selftest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SLH Investor Gateway")


@app.on_event("startup")
async def startup_event():
    try:
        init_db()
        logger.info("DB initialized")
    except Exception:
        logger.exception("DB init failed (startup). App will still boot, but DB features may be broken.")

    try:
        await initialize_bot()
        logger.info("Bot initialized")
    except Exception:
        logger.exception("Bot init failed (startup). App will still boot, but Telegram features may be broken.")


@app.get("/")
async def root():
    return {"message": "SLH Investor Gateway is running"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    # ready = health + deeper checks
    result = run_selftest(quick=True)
    return {"status": result.get("status", "unknown"), "checks": result.get("checks", [])}


@app.get("/selftest")
async def selftest():
    return run_selftest(quick=False)


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    # Telegram expects fast 200
    try:
        update_dict = await request.json()
    except Exception:
        logger.warning("Webhook received invalid JSON")
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=status.HTTP_200_OK)

    try:
        await process_webhook(update_dict)
        return JSONResponse({"ok": True}, status_code=status.HTTP_200_OK)
    except Exception:
        logger.exception("Webhook processing failed")
        return JSONResponse({"ok": False}, status_code=status.HTTP_200_OK)
