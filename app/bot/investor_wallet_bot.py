# app/bot/investor_wallet_bot.py
from __future__ import annotations

import logging
from decimal import Decimal
from datetime import date

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from app.core.config import settings
from app.database import SessionLocal
from app import crud, models, i18n

logger = logging.getLogger(__name__)

STATE_AWAITING_BNB_ADDRESS = "AWAITING_BNB_ADDRESS"


def _dec(x) -> Decimal:
    return Decimal(str(x))


class InvestorWalletBot:
    def __init__(self):
        self.application: Application | None = None
        self.bot: Bot | None = None

    def _db(self):
        return SessionLocal()

    def _is_admin(self, user_id: int) -> bool:
        return bool(settings.ADMIN_USER_ID) and str(user_id) == str(settings.ADMIN_USER_ID)

    def _is_investor_approved(self, user: models.User) -> bool:
        if not settings.INVESTOR_ONLY_MODE:
            return True
        status = (getattr(user, "investor_status", None) or "none").lower()
        role = (getattr(user, "role", None) or "user").lower()
        return status == "approved" or role == "investor"

    async def _require_investor(self, update: Update, user: models.User) -> bool:
        """Return True if allowed, otherwise reply with onboarding instructions."""
        if self._is_investor_approved(user):
            return True

        text = (
            "🔒 Investor-only area\n\n"
            "To access investor features you must complete onboarding.\n"
            "Use: /apply_investor\n\n"
            "You can still link your wallet and submit deposits.\n"
            "Commands: /link_wallet, /deposit, /mydeposits"
        )
        if update.message:
            await update.message.reply_text(text)
        else:
            # fallback (callback context)
            cq = update.callback_query
            if cq and cq.message:
                await cq.message.reply_text(text)
        return False

    def _get_lang(self, tg_user, context: ContextTypes.DEFAULT_TYPE | None = None) -> str:
        override = context.user_data.get("lang") if context else None
        if override:
            return i18n.normalize_lang(override)
        raw = getattr(tg_user, "language_code", None) or settings.DEFAULT_LANGUAGE
        return i18n.normalize_lang(raw)

    # =========================
    # Financial Gateway client
    # =========================

    def _gw_base(self) -> str:
        base = (getattr(settings, "FIN_GATEWAY_URL", "") or "").strip().rstrip("/")
        return base

    def _gw_headers(self) -> dict:
        token = (getattr(settings, "FIN_GATEWAY_TOKEN", "") or "").strip()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    async def _gw_get(self, path: str, params: dict | None = None) -> dict:
        base = self._gw_base()
        if not base:
            raise RuntimeError("FIN_GATEWAY_URL not set")
        url = f"{base}{path}"
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, params=params or {}, headers=self._gw_headers())
            r.raise_for_status()
            return r.json()

    async def _gw_post(self, path: str, payload: dict) -> dict:
        base = self._gw_base()
        if not base:
            raise RuntimeError("FIN_GATEWAY_URL not set")
        url = f"{base}{path}"
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload, headers=self._gw_headers())
            r.raise_for_status()
            return r.json()

    # =========================
    # Bot init
    # =========================

    async def initialize(self):
        if not settings.BOT_TOKEN:
            logger.warning("BOT_TOKEN not set - skipping bot init")
            return

        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        self.bot = self.application.bot

        # user
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("apply_investor", self.cmd_apply_investor))
        self.application.add_handler(CommandHandler("menu", self.cmd_menu))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("whoami", self.cmd_whoami))
        self.application.add_handler(CommandHandler("referrals", self.cmd_referrals))
        self.application.add_handler(CommandHandler("link_wallet", self.cmd_link_wallet))

        # investor flow (existing)
        self.application.add_handler(CommandHandler("invest", self.cmd_invest))
        self.application.add_handler(CommandHandler("deposit", self.cmd_deposit))
        self.application.add_handler(CommandHandler("balance", self.cmd_balance))
        self.application.add_handler(CommandHandler("history", self.cmd_history))

        # ILS / Financial Gateway (new)
        self.application.add_handler(CommandHandler("status_ils", self.cmd_status_ils))
        self.application.add_handler(CommandHandler("history_ils", self.cmd_history_ils))
        self.application.add_handler(CommandHandler("choose", self.cmd_choose))
        self.application.add_handler(CallbackQueryHandler(self.cb_choose, pattern=r"^CH_"))

        # admin
        self.application.add_handler(CommandHandler("admin_list_candidates", self.cmd_admin_list_candidates))
        self.application.add_handler(CommandHandler("admin_approve_investor", self.cmd_admin_approve_investor))
        self.application.add_handler(CommandHandler("admin_deposits", self.cmd_admin_deposits))
        self.application.add_handler(CommandHandler("admin_confirm_deposit", self.cmd_admin_confirm_deposit))

        # callbacks
        self.application.add_handler(CallbackQueryHandler(self.cb_menu, pattern=r"^M_"))

        # text handler
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text)
        )

        await self.application.initialize()

        if settings.WEBHOOK_URL:
            webhook_url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook/telegram"
            await self.bot.set_webhook(webhook_url)
            logger.info("Webhook set: %s", webhook_url)

        logger.info("InvestorWalletBot initialized")

    # ===== UI =====

    def _menu_kb(self, is_investor: bool) -> InlineKeyboardMarkup:
        rows = [
            [
                InlineKeyboardButton("👤 Profile", callback_data="M_WHOAMI"),
                InlineKeyboardButton("🎁 Referrals", callback_data="M_REF"),
            ],
            [
                InlineKeyboardButton("🔗 Link BNB", callback_data="M_LINK"),
                InlineKeyboardButton("💼 Invest", callback_data="M_INVEST"),
            ],
        ]
        if is_investor:
            rows.append(
                [
                    InlineKeyboardButton("💰 Balance", callback_data="M_BAL"),
                    InlineKeyboardButton("📥 Deposit", callback_data="M_DEP"),
                ]
            )
            rows.append([InlineKeyboardButton("🧾 History", callback_data="M_HIST")])

            # new: ILS quick actions (optional UI)
            rows.append(
                [
                    InlineKeyboardButton("₪ Status", callback_data="M_ILS_STATUS"),
                    InlineKeyboardButton("₪ Choose", callback_data="M_ILS_CHOOSE"),
                ]
            )
            rows.append([InlineKeyboardButton("₪ History", callback_data="M_ILS_HIST")])

        return InlineKeyboardMarkup(rows)

    async def _ensure_user(self, update: Update) -> models.User:
        db = self._db()
        try:
            tg = update.effective_user
            user = crud.get_or_create_user(db, tg.id, tg.username)
            return user
        finally:
            db.close()

    # ===== Commands =====

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            # create user
            user = crud.get_or_create_user(db, tg.id, tg.username)

            # referral: /start ref_<tid> (only first-time referral insert is prevented by crud)
            if context.args:
                raw = context.args[0]
                if isinstance(raw, str) and raw.startswith("ref_"):
                    try:
                        ref_tid = int(raw[4:])
                    except ValueError:
                        ref_tid = None
                    if ref_tid and ref_tid != tg.id:
                        reward = _dec(getattr(settings, "SLHA_REWARD_REFERRAL", "0.00001"))
                        crud.register_referral(db, tg.id, ref_tid, reward)

            is_investor = crud.is_investor_active(db, tg.id)
            text = (
                "ברוך הבא ל-SLH Global Investments\n\n"
                "✅ נוצר לך חשבון בסיסי.\n"
                "🎁 אפשר לשתף קישור רפררל כבר עכשיו.\n"
                "💼 מסלול השקעה (Investor Wallet) נפתח רק לאחר Onboarding ואישור אדמין.\n\n"
                "השתמש בתפריט:"
            )
            await update.message.reply_text(text, reply_markup=self._menu_kb(is_investor))
        finally:
            db.close()

    async def cmd_apply_investor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """User requests investor onboarding."""
        db = self._db()
        try:
            tg_user = update.effective_user
            user = crud.get_or_create_user(db, tg_user.id, tg_user.username)
            status = (user.investor_status or "none").lower()

            if status == "approved":
                await update.message.reply_text("✅ You are already approved as an investor.")
                return
            if status == "pending":
                await update.message.reply_text("⏳ Your investor onboarding is already pending approval.")
                return

            user.investor_status = "pending"
            db.add(user)
            db.commit()

            await update.message.reply_text(
                "✅ Investor onboarding request submitted.\n"
                "Our team will review and approve your access shortly."
            )

            # Notify admin logs
            if settings.LOG_NEW_USERS_CHAT_ID and self.application and self.application.bot:
                try:
                    target = int(settings.LOG_NEW_USERS_CHAT_ID)
                except Exception:
                    target = settings.LOG_NEW_USERS_CHAT_ID
                try:
                    await self.application.bot.send_message(
                        chat_id=target,
                        text=(
                            "📝 New investor onboarding request\n"
                            f"Telegram ID: {tg_user.id}\n"
                            f"Username: @{tg_user.username}"
                            if tg_user.username
                            else f"Telegram ID: {tg_user.id}\nUsername: N/A"
                        ),
                    )
                except Exception:
                    pass
        finally:
            db.close()

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = self._db()
        try:
            await self._ensure_user(update)
            is_investor = crud.is_investor_active(db, update.effective_user.id)
            await update.message.reply_text("בחר פעולה:", reply_markup=self._menu_kb(is_investor))
        finally:
            db.close()

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (
            "פקודות עיקריות:\n"
            "/start /menu\n"
            "/referrals\n"
            "/invest (פתיחת אונבורדינג השקעה)\n"
            "/deposit (דיווח הפקדה)\n"
            "/balance\n"
            "/history\n\n"
            "₪ / Financial Gateway:\n"
            "/status_ils\n"
            "/history_ils\n"
            "/choose\n\n"
            "אדמין:\n"
            "/admin_list_candidates\n"
            "/admin_approve_investor <telegram_id>\n"
            "/admin_deposits\n"
            "/admin_confirm_deposit <deposit_id> <credit_slh>\n"
        )
        await update.message.reply_text(text)

    async def cmd_whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = self._db()
        try:
            tg = update.effective_user
            user = crud.get_or_create_user(db, tg.id, tg.username)
            prof = db.query(models.InvestorProfile).filter(models.InvestorProfile.telegram_id == tg.id).first()
            w_inv = crud.get_wallet(db, tg.id, "investor")
            is_investor = crud.is_investor_active(db, tg.id)

            lines = []
            lines.append("👤 הפרופיל שלך")
            lines.append(f"Telegram ID: {tg.id}")
            lines.append(f"Username: @{tg.username}" if tg.username else "Username: N/A")
            lines.append(f"Role: {user.role}")
            lines.append(f"BNB address: {user.bnb_address or 'לא קושר'}")
            lines.append(f"SLHA points: {Decimal(user.slha_balance or 0):.8f}")

            if prof:
                lines.append("")
                lines.append("💼 Investor Profile:")
                lines.append(f"Status: {prof.status}")
                if w_inv:
                    lines.append(f"Investor wallet active: {bool(w_inv.is_active)}")
                    lines.append(f"Investor SLH: {Decimal(w_inv.balance_slh or 0):.4f}")
            else:
                lines.append("")
                lines.append("💼 עדיין אין Investor Profile. השתמש /invest.")

            if not is_investor:
                lines.append("\nℹ️ הפקדות מוכרות במערכת רק אחרי אישור אדמין למשקיע.")

            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    async def cmd_referrals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = self._db()
        try:
            tg = update.effective_user
            crud.get_or_create_user(db, tg.id, tg.username)

            # bot username for link
            bot_username = None
            try:
                me = await context.bot.get_me()
                bot_username = me.username
            except Exception:
                bot_username = None

            link = f"https://t.me/{bot_username}?start=ref_{tg.id}" if bot_username else "לא הצלחתי לקרוא bot username כרגע."
            count = crud.count_referrals(db, tg.id)

            user = db.query(models.User).filter(models.User.telegram_id == tg.id).first()
            slha = Decimal(user.slha_balance or 0) if user else Decimal("0")

            text = (
                "🎁 תוכנית הפניות\n\n"
                f"קישור אישי:\n{link}\n\n"
                f"מספר הפניות: {count}\n"
                f"יתרת SLHA: {slha:.8f}\n"
            )
            await update.message.reply_text(text)
        finally:
            db.close()

    async def cmd_link_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            user = crud.get_or_create_user(db, tg.id, tg.username)

            if context.args:
                addr = context.args[0].strip()
                if not addr.startswith("0x") or len(addr) < 20:
                    await update.message.reply_text("כתובת לא תקינה. דוגמה: /link_wallet 0xABC...")
                    return
                crud.set_bnb_address(db, user, addr)
                await update.message.reply_text(f"✅ נשמרה כתובת BNB:\n{addr}")
                context.user_data["state"] = None
                return

            context.user_data["state"] = STATE_AWAITING_BNB_ADDRESS
            await update.message.reply_text("שלח עכשיו כתובת BNB (מתחילה ב-0x...)")
        finally:
            db.close()

    async def cmd_invest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            crud.get_or_create_user(db, tg.id, tg.username)

            # אם כבר משקיע פעיל
            if crud.is_investor_active(db, tg.id):
                await update.message.reply_text("✅ אתה כבר משקיע מאושר. השתמש /deposit או /balance.")
                return

            # נרשום candidate + risk_ack=true
            prof = crud.start_invest_onboarding(
                db=db,
                telegram_id=tg.id,
                referrer_tid=None,
                risk_ack=True,
            )
            await update.message.reply_text(
                "💼 נפתח עבורך מסלול השקעה (Candidate).\n"
                "השלב הבא: אישור אדמין.\n"
                "לאחר אישור תוכל לדווח הפקדה דרך /deposit."
            )
        finally:
            db.close()

    async def cmd_deposit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            crud.get_or_create_user(db, tg.id, tg.username)

            if not crud.is_investor_active(db, tg.id):
                await update.message.reply_text(
                    "⛔ הפקדה במערכת זמינה רק למשקיע מאושר.\n"
                    "בצע /invest ואז המתן לאישור אדמין."
                )
                return

            ton_addr = getattr(settings, "TON_COMMUNITY_WALLET_ADDRESS", None) or "NOT_SET"
            text = (
                "📥 דיווח הפקדה (Deposit)\n\n"
                "שלב 1: העבר לכתובת ה-TON הבאה:\n"
                f"{ton_addr}\n\n"
                "שלב 2: דווח כאן:\n"
                "שלח פקודה בפורמט:\n"
                "/deposit_report <amount> <currency> [tx_hash]\n\n"
                "דוגמה:\n"
                "/deposit_report 100 TON\n"
            )
            await update.message.reply_text(text)
        finally:
            db.close()

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            crud.get_or_create_user(db, tg.id, tg.username)

            if not crud.is_investor_active(db, tg.id):
                await update.message.reply_text("אין לך Investor Wallet פעיל עדיין. /invest ואז אישור אדמין.")
                return

            w = crud.get_wallet(db, tg.id, "investor")
            bal = Decimal(w.balance_slh or 0) if w else Decimal("0")
            await update.message.reply_text(f"💰 יתרת משקיע פנימית:\n{bal:.4f} SLH")
        finally:
            db.close()

    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            crud.get_or_create_user(db, tg.id, tg.username)
            txs = (
                db.query(models.Transaction)
                .filter((models.Transaction.from_user == tg.id) | (models.Transaction.to_user == tg.id))
                .order_by(models.Transaction.created_at.desc())
                .limit(20)
                .all()
            )
            if not txs:
                await update.message.reply_text("אין היסטוריה עדיין.")
                return

            lines = ["🧾 היסטוריית אירועים (20 אחרונים):", ""]
            for tx in txs:
                ts = tx.created_at.strftime("%Y-%m-%d %H:%M") if tx.created_at else "N/A"
                lines.append(f"[{ts}] {tx.tx_type} | amount={Decimal(tx.amount_slh or 0):.4f} | id={tx.id}")
            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    # =========================
    # NEW: ILS commands (Gateway)
    # =========================

    async def cmd_status_ils(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user

        # ensure local user exists (keeps your current DB logic intact)
        db = self._db()
        try:
            user = crud.get_or_create_user(db, tg.id, tg.username)
            # Optional: if you want investor gating
            # if not await self._require_investor(update, user):
            #     return
        finally:
            db.close()

        try:
            data = await self._gw_get("/investor/status", params={"user_id": tg.id})
            cap = float(data.get("capital_ils", 0) or 0)
            last = float(data.get("last_month_yield_ils", 0) or 0)
            alpha = data.get("last_month_alpha", None)
            choice = str(data.get("current_choice", "REINVEST") or "REINVEST").upper()

            alpha_txt = f"{alpha}" if alpha is not None else "N/A"
            choice_txt = "🔁 צבירה" if choice == "REINVEST" else "💸 קבלה"

            msg = (
                "💼 מצב השקעה (₪)\n\n"
                f"קרן נוכחית: ₪{cap:,.2f}\n"
                f"תשואת חודש אחרון: ₪{last:,.2f}\n"
                f"α (נזילות): {alpha_txt}\n"
                f"בחירה לחודש נוכחי: {choice_txt}\n\n"
                "לשינוי בחירה: /choose\n"
                "להיסטוריה: /history_ils"
            )
            await update.message.reply_text(msg)
        except Exception as e:
            await update.message.reply_text(
                "❌ לא הצלחתי לקרוא נתונים מהשער הפיננסי.\n"
                "בדוק ש-FIN_GATEWAY_URL מוגדר ושיש endpoints זמינים."
            )
            logger.exception("cmd_status_ils failed: %s", e)

    async def cmd_choose(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💸 קבל החודש", callback_data="CH_PAYOUT")],
            [InlineKeyboardButton("🔁 צבור לקרן", callback_data="CH_REINVEST")],
        ])
        await update.message.reply_text("בחר פעולה לחודש הנוכחי:", reply_markup=kb)

    async def cb_choose(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        tg = update.effective_user

        action = (q.data or "").replace("CH_", "").strip().upper()
        choice = "PAYOUT" if action == "PAYOUT" else "REINVEST"
        month = date.today().replace(day=1).isoformat()

        try:
            await self._gw_post("/investor/choice", {
                "user_id": tg.id,
                "month": month,
                "choice": choice
            })
            txt = "✅ עודכן: 💸 קבלה" if choice == "PAYOUT" else "✅ עודכן: 🔁 צבירה"
            if q.message:
                await q.message.reply_text(txt)
        except Exception as e:
            if q.message:
                await q.message.reply_text("❌ לא הצלחתי לעדכן בחירה בשער הפיננסי.")
            logger.exception("cb_choose failed: %s", e)

    async def cmd_history_ils(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        try:
            data = await self._gw_get("/investor/history", params={"user_id": tg.id, "limit": 20})
            items = data.get("items", []) or []
            if not items:
                await update.message.reply_text("אין היסטוריה (₪) עדיין.")
                return

            lines = ["🧾 היסטוריה (₪) — 20 אחרונים:", ""]
            for it in items:
                d = it.get("date", "")
                t = it.get("type", "")
                a = float(it.get("amount_ils", 0) or 0)
                s = it.get("source", "")
                lines.append(f"[{d}] {t} ₪{a:,.2f} ({s})")
            await update.message.reply_text("\n".join(lines))
        except Exception as e:
            await update.message.reply_text("❌ לא הצלחתי לקרוא היסטוריה מהשער הפיננסי.")
            logger.exception("cmd_history_ils failed: %s", e)

    # ===== Admin =====

    async def cmd_admin_list_candidates(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("Admin only.")
            return

        db = self._db()
        try:
            cands = (
                db.query(models.InvestorProfile)
                .filter(models.InvestorProfile.status == "candidate")
                .order_by(models.InvestorProfile.created_at.asc())
                .limit(50)
                .all()
            )
            if not cands:
                await update.message.reply_text("אין מועמדים כרגע.")
                return

            lines = ["👮 Candidates (עד 50):", ""]
            for p in cands:
                lines.append(f"- {p.telegram_id} | risk_ack={p.risk_ack} | created={p.created_at}")
            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    async def cmd_admin_approve_investor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("Admin only.")
            return

        parts = (update.message.text or "").split()
        if len(parts) != 2:
            await update.message.reply_text("Usage: /admin_approve_investor <telegram_id>")
            return

        try:
            tid = int(parts[1])
        except ValueError:
            await update.message.reply_text("Invalid telegram_id")
            return

        db = self._db()
        try:
            crud.get_or_create_user(db, tid, None)
            prof = crud.approve_investor(db, admin_tid=update.effective_user.id, telegram_id=tid)
            await update.message.reply_text(f"✅ Approved investor: {tid} (status={prof.status})")
        finally:
            db.close()

    async def cmd_admin_deposits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("Admin only.")
            return

        db = self._db()
        try:
            deps = crud.list_pending_deposits(db, limit=50)
            if not deps:
                await update.message.reply_text("אין הפקדות pending.")
                return

            lines = ["📥 Pending deposits (עד 50):", ""]
            for d in deps:
                lines.append(
                    f"- id={d.id} user={d.telegram_id} {d.amount} {d.currency} net={d.network} hash={d.tx_hash or '-'}"
                )
            lines.append("")
            lines.append("אישור: /admin_confirm_deposit <deposit_id> <credit_slh>")
            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    async def cmd_admin_confirm_deposit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("Admin only.")
            return

        parts = (update.message.text or "").split()
        if len(parts) != 3:
            await update.message.reply_text("Usage: /admin_confirm_deposit <deposit_id> <credit_slh>")
            return

        try:
            dep_id = int(parts[1])
            credit_slh = Decimal(parts[2])
        except Exception:
            await update.message.reply_text("Invalid parameters.")
            return

        db = self._db()
        try:
            dep = crud.confirm_deposit_and_credit(
                db,
                admin_tid=update.effective_user.id,
                deposit_id=dep_id,
                credit_slh=credit_slh,
            )
            await update.message.reply_text(
                f"✅ Deposit confirmed.\n"
                f"deposit_id={dep.id}\n"
                f"user={dep.telegram_id}\n"
                f"credited={credit_slh} SLH"
            )

            # NEW: also report DEPOSIT to Financial Gateway in ₪ (only if amount is already ₪)
            # If dep.amount is TON/USDT, DO NOT send as ₪. Add conversion layer later.
            try:
                # If your dep.currency is 'ILS' or 'NIS' -> safe as ₪
                cur = str(getattr(dep, "currency", "") or "").upper()
                if cur in ("ILS", "NIS", "₪"):
                    amount_ils = Decimal(str(dep.amount))
                    await self._gw_post("/ledger/event", {
                        "type": "DEPOSIT",
                        "user_id": int(dep.telegram_id),
                        "amount_ils": float(amount_ils),
                        "source": "admin_confirm_deposit",
                        "ref": f"deposit_id={dep.id}"
                    })
            except Exception:
                # don't fail admin flow if gateway is down
                pass

        except Exception as e:
            await update.message.reply_text(f"❌ Failed: {e}")
        finally:
            db.close()

    # ===== Callbacks =====

    async def cb_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        data = q.data

        fake_update = Update(update.update_id, message=q.message)

        if data == "M_WHOAMI":
            await self.cmd_whoami(fake_update, context)
        elif data == "M_REF":
            await self.cmd_referrals(fake_update, context)
        elif data == "M_LINK":
            await self.cmd_link_wallet(fake_update, context)
        elif data == "M_INVEST":
            await self.cmd_invest(fake_update, context)
        elif data == "M_BAL":
            await self.cmd_balance(fake_update, context)
        elif data == "M_DEP":
            await self.cmd_deposit(fake_update, context)
        elif data == "M_HIST":
            await self.cmd_history(fake_update, context)

        # new menu actions:
        elif data == "M_ILS_STATUS":
            await self.cmd_status_ils(fake_update, context)
        elif data == "M_ILS_CHOOSE":
            await self.cmd_choose(fake_update, context)
        elif data == "M_ILS_HIST":
            await self.cmd_history_ils(fake_update, context)

    # ===== Text =====

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        state = context.user_data.get("state")
        text = (update.message.text or "").strip()
        tg = update.effective_user

        # Deposit report command as plain text (fast path)
        if text.startswith("/deposit_report"):
            parts = text.split()
            if len(parts) < 3:
                await update.message.reply_text("Usage: /deposit_report <amount> <currency> [tx_hash]")
                return
            amount = parts[1]
            currency = parts[2]
            tx_hash = parts[3] if len(parts) >= 4 else None

            db = self._db()
            try:
                crud.get_or_create_user(db, tg.id, tg.username)

                if not crud.is_investor_active(db, tg.id):
                    await update.message.reply_text("⛔ רק משקיע מאושר יכול לדווח הפקדה.")
                    return

                dep = crud.create_deposit(
                    db,
                    telegram_id=tg.id,
                    network="TON",
                    currency=currency,
                    amount=amount,
                    tx_hash=tx_hash,
                    note=None,
                )
                await update.message.reply_text(f"✅ נוצר דיווח הפקדה (pending). id={dep.id}\nאדמין יאשר ויזכה SLH.")
            finally:
                db.close()
            return

        # link wallet state
        if state == STATE_AWAITING_BNB_ADDRESS:
            if not text.startswith("0x") or len(text) < 20:
                await update.message.reply_text("כתובת לא תקינה. נסה שוב /link_wallet.")
                return
            db = self._db()
            try:
                user = crud.get_or_create_user(db, tg.id, tg.username)
                crud.set_bnb_address(db, user, text)
                context.user_data["state"] = None
                await update.message.reply_text(f"✅ נשמרה כתובת BNB:\n{text}")
            finally:
                db.close()
            return

        # default
        await update.message.reply_text("לא הבנתי. השתמש /menu")


_bot_instance = InvestorWalletBot()


async def initialize_bot():
    await _bot_instance.initialize()


async def process_webhook(update_dict: dict):
    if not _bot_instance.application:
        logger.error("Application is not initialized")
        return
    update = Update.de_json(update_dict, _bot_instance.application.bot)
    await _bot_instance.application.process_update(update)
