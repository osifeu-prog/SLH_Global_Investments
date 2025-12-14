# app/main.py
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.database import init_db
from app.bot.investor_wallet_bot import initialize_bot, process_webhook
from app.monitoring import run_selftest

logger = logging.getLogger(__name__)

app = FastAPI(title="SLH Investor Gateway")


@app.on_event("startup")
async def startup_event():
    # חשוב: קודם DB, ואז הבוט
    try:
        init_db()
        logger.info("DB initialized")
    except Exception:
        logger.exception("DB init failed (startup). Continuing to boot app.")

    try:
        await initialize_bot()
        logger.info("Bot initialized")
    except Exception:
        logger.exception("Bot init failed (startup). Continuing to boot app.")


@app.get("/")
async def root():
    return {"message": "SLH Investor Gateway is running"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    result = run_selftest(quick=True)
    return {"status": result.get("status", "unknown"), "checks": result.get("checks", [])}


@app.get("/selftest")
async def selftest():
    return run_selftest(quick=False)


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    Telegram expects fast 200 responses.
    Even if we hit an internal exception, we return 200 to avoid retries storms.
    """
    try:
        update_dict = await request.json()
    except Exception:
        # גוף לא תקין — עדיין מחזירים 200 כדי לא להיכנס ללופ ריטרייז
        logger.warning("Webhook received invalid JSON")
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=status.HTTP_200_OK)

    try:
        await process_webhook(update_dict)
        return JSONResponse({"ok": True}, status_code=status.HTTP_200_OK)
    except Exception:
        logger.exception("Webhook processing failed")
        # fallback: אל תפיל את webhook (טלגרם ינסה שוב אם לא 200)
        return JSONResponse({"ok": False}, status_code=status.HTTP_200_OK)
