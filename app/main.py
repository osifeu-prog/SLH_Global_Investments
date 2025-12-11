from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.database import init_db
from app.bot.investor_wallet_bot import initialize_bot, process_webhook
from app.monitoring import run_selftest

app = FastAPI(title="SLH Investor Gateway")


@app.on_event("startup")
async def startup_event():
    init_db()
    await initialize_bot()


@app.get("/")
async def root():
    return {"message": "SLH Investor Gateway is running"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    result = run_selftest(quick=True)
    return {"status": result["status"], "checks": result["checks"]}


@app.get("/selftest")
async def selftest():
    return run_selftest(quick=False)


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    update_dict = await request.json()
    await process_webhook(update_dict)
    return JSONResponse({"ok": True}, status_code=status.HTTP_200_OK)
