# Stage 2 Fix Pack (Bot + DB + Docs)

## Why it crashed
Your `app/models.py` got overwritten so the new classes were placed **before** `Base = declarative_base()`.
That causes:
`NameError: name 'Base' is not defined`.

## Safe recovery (fastest)
1) Revert `app/models.py` to the last working version (the one that ran /health ok).
2) Then append the Stage 2 classes **at the end of the file** (after all other models).

If you don't remember the commit:
- In GitHub: open **Commits**, find the last green / working deployment commit, and copy its SHA.
- Locally:
  - `git log --oneline -- app/models.py`
  - `git checkout <SHA> -- app/models.py`

## Files to update (minimum set)
- `app/models.py` → append `InternalTransfer` + `RedemptionRequest` (see `app/stage2_models_append.py`).
- `app/database.py` → add CREATE TABLE IF NOT EXISTS statements (see `app/stage2_database_sql_append.txt`) inside `_ensure_schema()`.
- `app/crud.py` → append functions for transfers & redemption (see `app/stage2_crud_append.py`).
- `app/bot/investor_wallet_bot.py` → add handlers + implementations (see `app/stage2_bot_patch.py`).

## Deploy order
1) Push fixes to GitHub
2) Railway redeploy
3) Confirm:
- `/health` `/ready` `/selftest`
4) Telegram tests (see below)

## Telegram tests (step-by-step)
### A) Create SLHA balance
Use your existing monthly reward, or for quick test credit SLHA via admin:
- Add the admin command below (in bot patch).
- Run:
`/admin_credit 224223270 100 SLHA`

### B) Transfer
`/transfer 224223270 1`
(transfer to yourself should be blocked – test with another user ID)

### C) Redemption request
`/redeem 10`
Then admin:
`/admin_redemptions`
`/admin_approve_redeem <id>`

**Important:** on-chain is NOT executed. It only records an approved redemption and leaves a hook.

## Investor pages
Replace:
- `docs/index.html`
- `docs/investors.html`
with the ones in this pack (much richer explanations and investor-friendly).
