# SLH Finance – Monorepo Package

This ZIP bundles **three** main parts of the SLH Finance stack:

1. `app/` – FastAPI + Telegram backend (Railway)
2. `admin_panel/` – React + Vite + Tailwind admin dashboard (Vercel)
3. `docs/` – Static marketing & investor docs (GitHub Pages / Vercel static)

## 1. Backend API (Railway – `app/`)

### Local run

```bash
cd app
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate
pip install -r ../requirements.txt
uvicorn app.main:app --reload --port 8080
```

The important endpoints:

- `GET /health` – basic liveness
- `GET /ready` – deeper readiness (DB, env, BSC)
- `GET /selftest` – detailed self-test for admin
- `POST /webhook/telegram` – Telegram webhook entrypoint

The Telegram bot is defined in `app/bot/investor_wallet_bot.py`
and is initialized from `app/main.py` at startup.

### Railway deployment

1. Push this repo to GitHub.
2. Create a **Railway** project and attach the repo.
3. Ensure build is **Dockerfile** based and root path is repo root.
4. In Railway → Variables define:

   - `BOT_TOKEN`
   - `DATABASE_URL` (Postgres)
   - `SECRET_KEY`
   - `ADMIN_USER_ID`
   - `WEBHOOK_URL` (your Railway URL)
   - `COMMUNITY_WALLET_ADDRESS`, `COMMUNITY_WALLET_PRIVATE_KEY`
   - `SLH_TOKEN_ADDRESS`, `SLH_TOKEN_DECIMALS`, `SLH_PRICE_NIS`
   - `BSC_RPC_URL`, `BSC_SCAN_BASE`
   - `DOCS_URL`, `PUBLIC_BASE_URL`
   - `MAIN_COMMUNITY_CHAT_ID`, `LOG_*_CHAT_ID`, `REFERRAL_LOGS_CHAT_ID`
   - `DEFAULT_LANGUAGE`
   - `SUPPORTED_LANGUAGES`
   - `OPENAI_API_KEY` (for AI modules – optional but recommended)

5. Set the **start command** (if not in Dockerfile) to:

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8080
   ```

6. Healthcheck path should be `/health`.

After the deploy is **green**, configure Telegram webhook:

```text
WEBHOOK_URL = https://<your-service>.railway.app
```

The code will automatically set:

```text
<WEBHOOK_URL>/webhook/telegram
```

when the bot starts.

## 2. Admin Panel (Vercel – `admin_panel/`)

The admin panel is a Vite + React + Tailwind SPA designed to be deployed on Vercel.

### Local run

```bash
cd admin_panel
npm install
npm run dev
```

Open http://localhost:5173.

### Deploy on Vercel

1. Create a new Vercel project from the **same GitHub repo**.
2. Set the **root directory** to `admin_panel/`.
3. Build command: `npm run build`.
4. Output directory: `dist`.
5. Set environment variables as needed to point to your Railway API, e.g.:

   - `VITE_API_BASE_URL=https://tease-production.up.railway.app`

Once deployed, you'll get something like:

```text
https://slhfinance.vercel.app
```

## 3. Docs site (GitHub Pages – `docs/`)

The `docs/` folder contains:

- `index.html`
- `investors.html`
- `assets/slh-social-cover.png`

For GitHub Pages:

1. Push this repo to GitHub.
2. In repo → Settings → Pages:
   - Source: **Deploy from branch**
   - Branch: `main`
   - Folder: `/docs`
3. After a few minutes you'll get:

   ```text
   https://<username>.github.io/<reponame>/
   ```

For your case this can become:

```text
https://osifeu-prog.github.io/slhfinance/
```

(Rename repo to `slhfinance` if you like.)

## 4. Suggested domain wiring

- Backend (Railway): `slhfinance.railway.app`
- Admin panel (Vercel): `slhfinance.vercel.app`
- Docs (GitHub Pages): `osifeu-prog.github.io/slhfinance`

Later, when you buy a real domain (for example `slhfinance.ai`):

- Point `api.slhfinance.ai` → Railway
- Point `app.slhfinance.ai` → Vercel
- Point `www.slhfinance.ai` → either Vercel or GitHub Pages

## 5. How to smoke-test everything (real money ready)

1. **Check backend health**

   - Open `https://<railway-app>.railway.app/health` – should be `{"status":"ok"}`.
   - Open `https://<railway-app>.railway.app/ready` – DB and BSC should be `ok`.

2. **Check Telegram bot**

   - Send `/ping` → get `pong`.
   - Send `/language` → choose a language → get confirmation.
   - Send `/start` → see the investor onboarding message.
   - Link BNB wallet with `/link_wallet` and an address.
   - As admin, run `/admin_selftest` and check all modules.

3. **Check SLH / SLHA logic**

   - Use `/admin_credit <telegram_id> <amount>` to credit SLH.
   - Trigger referral flows (as defined in the Python code) and verify SLHA balance fields.
   - Use `/history` to see internal ledger entries.
   - Use `/summary` to view full dashboard per investor.

4. **Check admin panel**

   - Open `https://slhfinance.vercel.app`.
   - Verify demo stats and status cards show up.
   - Later you can connect real data via API calls to the Railway backend.

Once all of the above pass with your friend’s test deposit recorded in the system,
you can consider this stack “real money ready” for a limited pilot.
