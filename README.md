# SLH Global Investments

מערכת השקעות/משקיעים מבוססת:
- FastAPI (API + Webhook ל־Telegram)
- PostgreSQL (Ledger פנימי + טבלאות מערכת)
- Bot טלגרם להצגת פרופיל, יתרות, דוחות, הפניות, ובקשות השקעה/פדיון
- דפי מידע סטטיים למשקיעים (GitHub Pages תחת `docs/`)

> המערכת מספקת מידע ותיעוד תפעולי. אינה ייעוץ השקעות.

## מה עובד כרגע (Production)

### Endpoints
- `GET /health` – סטטוס בסיסי
- `GET /ready` – בדיקות חיות (ENV + DB)
- `GET /selftest` – בדיקות חיות (ENV + DB + BSC RPC)

### Telegram Bot (Webhook)
הבוט מאפשר:
- `/start`, `/menu`, `/help`
- `/whoami` – פרופיל משקיע
- `/wallet` – רשימת ארנקים פנימיים (base / investor)
- `/balance` – יתרות לפי Ledger פנימי
- `/statement` – תנועות אחרונות
- `/referrals` – קישור אישי + מונה הפניות
- `/invest` – בקשת השקעה (נפתח Investor Wallet אחרי אישור אדמין)
- `/link_wallet` – קישור כתובת BNB

## Stage 2: העברות פנימיות + פדיון (SLHA)

### העברת SLHA בין משתמשים
- `/transfer <telegram_id> <amount>`

העברה נרשמת:
- כ־Ledger OUT אצל השולח
- כ־Ledger IN אצל המקבל
- ובטבלת `internal_transfers` לצורכי Audit

### בקשת פדיון SLHA (עם נעילה)
- `/redeem <amount> [regular|early] [payout_address(optional)]`

בעת פתיחת בקשה הסכום “ננעל” ב־Ledger כדי למנוע העברה כפולה בזמן המתנה.
דחייה משחררת את הנעילה.

### אדמין
- `/admin_redemptions [status]`
- `/admin_approve_redeem <id>`
- `/admin_reject_redeem <id> [note]`

## On-chain (מוכן, כבוי)
יש Hook מוכן לפדיון SLH און־צ’יין (`send_slh_onchain`) אך הוא **כבוי בכוונה** ולא שולח שום דבר אוטומטית.

## הרצה מקומית

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# נדרש PostgreSQL + DATABASE_URL
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

## משתני סביבה (Railway)
העיקריים:
- `DATABASE_URL`
- `BOT_TOKEN` (אופציונלי – אם חסר, הבוט מנוטרל)
- `WEBHOOK_URL` (אופציונלי – אם קיים, הבוט מגדיר webhook אוטומטי)
- `ADMIN_USER_ID`

## GitHub Pages (דפי משקיעים)
התיקייה `docs/` מכילה:
- `docs/index.html` – שער משקיעים
- `docs/investors.html` – דף מידע מלא למשקיעים
