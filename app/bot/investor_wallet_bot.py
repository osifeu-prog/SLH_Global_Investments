# app/bot/investor_wallet_bot.py
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
from app import models, crud, ledger
from app.monitoring import run_selftest
from app.yield_engine import run_daily_interest_accrual

logger = logging.getLogger(__name__)

STATE_AWAITING_BNB_ADDRESS = "AWAITING_BNB_ADDRESS"


def _dec(x) -> Decimal:
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def _parse_decimal(s: str) -> Decimal:
    return Decimal(str(s).strip())


class InvestorWalletBot:
    def __init__(self):
        self.application: Application | None = None
        self._bot_username: str | None = None

    def _db(self):
        return SessionLocal()

    def _is_admin(self, telegram_id: int) -> bool:
        return bool(settings.ADMIN_USER_ID) and str(telegram_id) == str(settings.ADMIN_USER_ID)

    def _menu_markup(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("👤 פרופיל", callback_data="MENU:WHOAMI"),
                    InlineKeyboardButton("💼 ארנקים", callback_data="MENU:WALLETS"),
                ],
                [
                    InlineKeyboardButton("💰 הפקדה", callback_data="MENU:DEPOSIT"),
                    InlineKeyboardButton("📊 יתרה", callback_data="MENU:BALANCE"),
                ],
                [
                    InlineKeyboardButton("🧾 דוח תנועות", callback_data="MENU:STATEMENT"),
                    InlineKeyboardButton("📈 סיכום משקיע", callback_data="MENU:SUMMARY"),
                ],
                [
                    InlineKeyboardButton("🎁 הפניות", callback_data="MENU:REFERRALS"),
                    InlineKeyboardButton("📥 בקשת השקעה", callback_data="MENU:INVEST"),
                ],
                [
                    InlineKeyboardButton("🔗 קישור כתובת BNB", callback_data="MENU:LINK_BNB"),
                    InlineKeyboardButton("🛠 אדמין", callback_data="MENU:ADMIN"),
                ],
            ]
        )

    def _admin_markup(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📊 סטטוס מערכת", callback_data="ADMIN:STATUS")],
                [InlineKeyboardButton("✅ אישור משקיע", callback_data="ADMIN:APPROVE")],
                [InlineKeyboardButton("💳 זיכוי (Credit)", callback_data="ADMIN:CREDIT")],
                [InlineKeyboardButton("🧾 Ledger גלובלי", callback_data="ADMIN:LEDGER")],
                [InlineKeyboardButton("📈 ריבית יומית", callback_data="ADMIN:ACCRUE")],
                [InlineKeyboardButton("🧪 Selftest", callback_data="ADMIN:SELFTEST")],
            ]
        )

    async def initialize(self):
        if not settings.BOT_TOKEN:
            logger.warning("BOT_TOKEN missing, bot disabled")
            return

        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        self._bot_username = (await self.application.bot.get_me()).username

        # User commands
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("menu", self.cmd_menu))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("whoami", self.cmd_whoami))
        self.application.add_handler(CommandHandler("wallet", self.cmd_wallet))
        self.application.add_handler(CommandHandler("referrals", self.cmd_referrals))
        self.application.add_handler(CommandHandler("invest", self.cmd_invest))
        self.application.add_handler(CommandHandler("link_wallet", self.cmd_link_wallet))
        self.application.add_handler(CommandHandler("deposit", self.cmd_deposit))
        self.application.add_handler(CommandHandler("balance", self.cmd_balance))
        self.application.add_handler(CommandHandler("statement", self.cmd_statement))
        self.application.add_handler(CommandHandler("summary", self.cmd_summary))
        self.application.add_handler(CommandHandler("admin", self.cmd_admin))

        # Admin commands (direct)
        self.application.add_handler(CommandHandler("admin_credit", self.cmd_admin_credit))
        self.application.add_handler(CommandHandler("admin_ledger", self.cmd_admin_ledger))
        self.application.add_handler(CommandHandler("admin_accrue_interest", self.cmd_admin_accrue_interest))
        self.application.add_handler(CommandHandler("admin_selftest", self.cmd_admin_selftest))

        # Callback menu
        self.application.add_handler(CallbackQueryHandler(self.cb_menu))

        # Text handler
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

        # Error handler
        self.application.add_error_handler(self.on_error)

        await self.application.initialize()

        if settings.WEBHOOK_URL:
            url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook/telegram"
            await self.application.bot.set_webhook(url)
            logger.info(f"Webhook set: {url}")

        logger.info("InvestorWalletBot initialized")

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.exception("Unhandled bot error", exc_info=context.error)
        try:
            if isinstance(update, Update):
                msg = update.effective_message
                if msg:
                    await msg.reply_text("⚠️ תקלה זמנית. נסה שוב /menu")
        except Exception:
            pass

    # -------- internal ensure --------

    def _ensure_base_wallet(self, db, telegram_id: int):
        crud.get_or_create_wallet(
            db,
            telegram_id=telegram_id,
            wallet_type="base",
            kind="base",
            deposits_enabled=True,
            withdrawals_enabled=False,
        )

    def _ensure_investor_wallet(self, db, telegram_id: int):
        crud.get_or_create_wallet(
            db,
            telegram_id=telegram_id,
            wallet_type="investor",
            kind="investor",
            deposits_enabled=True,
            withdrawals_enabled=False,
        )

    # -------- Commands (User) --------

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        start_payload = (context.args[0] if context.args else None)

        db = self._db()
        try:
            crud.get_or_create_user(db, tg.id, tg.username)
            self._ensure_base_wallet(db, tg.id)

            # referral capture: /start ref_<id>
            if start_payload and start_payload.startswith("ref_"):
                try:
                    referrer_tid = int(start_payload.replace("ref_", "").strip())
                    created = crud.apply_referral(db, referrer_tid, tg.id)
                    if created:
                        reward = getattr(settings, "SLHA_REWARD_REFERRAL", None)
                        if reward:
                            ref_user = crud.get_or_create_user(db, referrer_tid, None)
                            ref_user.slha_balance = _dec(ref_user.slha_balance) + _dec(reward)
                            db.add(ref_user)
                            db.commit()
                except Exception:
                    pass

            txt = (
                "ברוך הבא ל-SLH Global Investments\n\n"
                "✅ נוצר לך חשבון בסיסי.\n"
                "💼 מסלול השקעה (Investor Wallet) נפתח רק לאחר בקשה ואישור אדמין.\n\n"
                "בחר פעולה:"
            )
            await update.message.reply_text(txt, reply_markup=self._menu_markup())
        finally:
            db.close()

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = self._db()
        try:
            self._ensure_base_wallet(db, update.effective_user.id)
        finally:
            db.close()
        await update.message.reply_text("תפריט ראשי:", reply_markup=self._menu_markup())

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        txt = (
            "פקודות:\n"
            "/menu – תפריט\n"
            "/whoami – פרופיל\n"
            "/wallet – ארנקים\n"
            "/deposit – הפקדה\n"
            "/balance – יתרה\n"
            "/statement – דוח תנועות\n"
            "/summary – סיכום משקיע\n"
            "/referrals – הפניות\n"
            "/invest – בקשת השקעה\n"
            "/link_wallet – קישור כתובת BNB\n"
        )
        if self._is_admin(update.effective_user.id):
            txt += (
                "\n\nאדמין:\n"
                "/admin – פאנל אדמין\n"
                "/admin_credit <tid> <amount> [currency]\n"
                "/admin_ledger\n"
                "/admin_accrue_interest [apr] [currency] [YYYY-MM-DD]\n"
                "/admin_selftest\n"
            )
        await update.message.reply_text(txt)

    async def cmd_whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            user = crud.get_or_create_user(db, tg.id, tg.username)
            prof = crud.get_investor_profile(db, tg.id)

            status = "אין" if not prof else str(prof.status)
            txt = (
                "👤 פרופיל\n\n"
                f"ID: {tg.id}\n"
                f"שם משתמש: @{tg.username}\n"
                f"BNB: {user.bnb_address or 'לא מחובר'}\n"
                f"SLH (פנימי): {_dec(user.balance_slh):,.6f}\n"
                f"SLHA (נקודות): {_dec(user.slha_balance):,.8f}\n\n"
                f"סטטוס משקיע: {status}\n"
            )
            await update.message.reply_text(txt)
        finally:
            db.close()

    async def cmd_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            self._ensure_base_wallet(db, tg.id)

            wallets = (
                db.query(models.Wallet)
                .filter(models.Wallet.telegram_id == tg.id)
                .order_by(models.Wallet.wallet_type.asc())
                .all()
            )

            lines = ["💼 הארנקים שלך:\n"]
            for w in wallets:
                lines.append(
                    f"- {w.wallet_type.upper()} | סוג: {w.kind} | "
                    f"הפקדות: {'✅' if w.deposits_enabled else '❌'} | "
                    f"משיכות: {'✅' if w.withdrawals_enabled else '❌'}"
                )

            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    async def cmd_referrals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            count = crud.count_referrals(db, tg.id)
            bot_username = self._bot_username or "YOUR_BOT"
            link = f"https://t.me/{bot_username}?start=ref_{tg.id}"
            txt = (
                "🎁 תוכנית הפניות\n\n"
                f"קישור אישי:\n{link}\n\n"
                f"מספר הפניות: {count}\n"
            )
            await update.message.reply_text(txt)
        finally:
            db.close()

    async def cmd_link_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data["state"] = STATE_AWAITING_BNB_ADDRESS
        await update.message.reply_text("שלח עכשיו כתובת BNB (מתחילה ב-0x...)")

    async def cmd_invest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            self._ensure_base_wallet(db, tg.id)

            if crud.is_investor_active(db, tg.id):
                await update.message.reply_text("✅ כבר יש לך סטטוס משקיע פעיל.")
                return

            ref = (
                db.query(models.Referral)
                .filter(models.Referral.referred_tid == tg.id)
                .order_by(models.Referral.id.desc())
                .first()
            )
            referrer_tid = ref.referrer_tid if ref else None

            crud.start_invest_onboarding(db, tg.id, referrer_tid=referrer_tid, note="Requested via bot")
            self._ensure_investor_wallet(db, tg.id)

            await update.message.reply_text(
                "📥 בקשת השקעה נשלחה.\n\n"
                "נפתח לך ארנק משקיע (הפקדות בלבד).\n"
                "לאחר אישור אדמין – הסטטוס יעודכן.\n\n"
                "בינתיים אפשר להפקיד, עם Memo לפי ה-ID שלך."
            )
        finally:
            db.close()

    async def cmd_deposit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        asset = (settings.DEFAULT_DEPOSIT_ASSET or "USDT_TON").upper()
        addr = settings.USDT_TON_TREASURY_ADDRESS if asset == "USDT_TON" else settings.TON_TREASURY_ADDRESS
        addr = addr or settings.TON_TREASURY_ADDRESS or "MISSING_TREASURY_ADDRESS"

        txt = (
            "💰 הפקדה\n\n"
            f"שלח {('USDT (על TON)' if asset == 'USDT_TON' else 'TON')} לכתובת הבאה:\n"
            f"{addr}\n\n"
            f"חשוב: הוסף Memo/Comment (הערה) = {tg.id}\n"
            "ככה נוכל להצמיד הפקדה למשתמש בצורה חד-משמעית.\n\n"
            "ארנק יעד במערכת: investor\n"
        )
        await update.message.reply_text(txt)

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            usdt = ledger.get_balance(db, telegram_id=tg.id, wallet_type="investor", currency="USDT_TON")
            ton = ledger.get_balance(db, telegram_id=tg.id, wallet_type="investor", currency="TON")
            apr = settings.DEFAULT_APR or "0.18"
            txt = (
                "📊 יתרה (לפי Ledger פנימי)\n\n"
                f"USDT_TON: {usdt:,.6f}\n"
                f"TON: {ton:,.6f}\n\n"
                f"APR תצוגה/תוכנית: {apr}\n"
            )
            await update.message.reply_text(txt)
        finally:
            db.close()

    async def cmd_statement(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            rows = ledger.get_statement(db, telegram_id=tg.id, wallet_type="investor", limit=15)
            if not rows:
                await update.message.reply_text("🧾 אין תנועות עדיין.")
                return

            lines = ["🧾 דוח תנועות (15 אחרונות)\n"]
            for r in rows:
                lines.append(f"- #{r.id} | {r.created_at} | {r.direction.upper()} | {r.amount} {r.currency} | {r.reason}")
            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    async def cmd_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            prof = crud.get_investor_profile(db, tg.id)
            status = "none" if not prof else str(prof.status)
            usdt = ledger.get_balance(db, telegram_id=tg.id, wallet_type="investor", currency="USDT_TON")
            last = ledger.get_statement(db, telegram_id=tg.id, wallet_type="investor", limit=1)
            last_line = "אין עדיין" if not last else f"#{last[0].id} {last[0].reason} {last[0].amount} {last[0].currency}"

            txt = (
                "📈 סיכום משקיע\n\n"
                f"סטטוס: {status}\n"
                f"USDT_TON (חשבונאי): {usdt:,.6f}\n"
                f"עסקה אחרונה: {last_line}\n"
            )
            await update.message.reply_text(txt)
        finally:
            db.close()

    async def cmd_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("אין הרשאה.")
            return
        await update.message.reply_text("🛠 פאנל אדמין:", reply_markup=self._admin_markup())

    # -------- Admin commands (direct) --------

    async def cmd_admin_credit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("אין הרשאה.")
            return
        if len(context.args) < 2:
            await update.message.reply_text("שימוש: /admin_credit <telegram_id> <amount> [currency=USDT_TON]")
            return

        tid = int(context.args[0])
        amount = _parse_decimal(context.args[1])
        currency = (context.args[2] if len(context.args) >= 3 else "USDT_TON").upper()

        db = self._db()
        try:
            self._ensure_investor_wallet(db, tid)
            ledger.create_entry(
                db,
                telegram_id=tid,
                wallet_type="investor",
                direction="in",
                amount=amount,
                currency=currency,
                reason="admin_credit",
                meta={"by": str(update.effective_user.id)},
            )
            bal = ledger.get_balance(db, telegram_id=tid, wallet_type="investor", currency=currency)
            await update.message.reply_text(f"✅ זוכה {tid} ב-{amount} {currency}. יתרה חדשה: {bal}")
        finally:
            db.close()

    async def cmd_admin_ledger(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("אין הרשאה.")
            return
        db = self._db()
        try:
            rows = (
                db.query(models.LedgerEntry)
                .order_by(models.LedgerEntry.id.desc())
                .limit(50)
                .all()
            )
            if not rows:
                await update.message.reply_text("אין תנועות Ledger עדיין.")
                return
            lines = ["🧾 Ledger גלובלי (50 אחרונות)\n"]
            for r in rows:
                lines.append(f"- #{r.id} tid={r.telegram_id} {r.wallet_type} {r.direction} {r.amount} {r.currency} {r.reason}")
            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    async def cmd_admin_accrue_interest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("אין הרשאה.")
            return

        apr = _parse_decimal(context.args[0]) if len(context.args) >= 1 else _parse_decimal(settings.DEFAULT_APR or "0.18")
        currency = (context.args[1] if len(context.args) >= 2 else "USDT_TON").upper()
        day = date.fromisoformat(context.args[2]) if len(context.args) >= 3 else None

        db = self._db()
        try:
            res = run_daily_interest_accrual(db, apr=apr, currency=currency, wallet_type="investor", accrual_day=day)
            await update.message.reply_text(
                "📈 ריבית יומית בוצעה\n\n"
                f"processed={res.processed}\n"
                f"credited={res.credited}\n"
                f"skipped={res.skipped}\n"
                f"total_interest={res.total_interest}\n"
                f"apr={apr} currency={currency} day={(day.isoformat() if day else 'today')}"
            )
        finally:
            db.close()

    async def cmd_admin_selftest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("אין הרשאה.")
            return
        r = run_selftest(quick=False)
        lines = [f"🧪 Selftest: {r.get('status')}"]
        for c in r.get("checks", []):
            lines.append(f"- {c.get('name')}: {'OK' if c.get('ok') else 'FAIL'} {c.get('detail','')}".strip())
        await update.message.reply_text("\n".join(lines))

    # -------- Callback menu --------

    async def cb_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        data = q.data or ""
        tg = update.effective_user

        if data == "MENU:WHOAMI":
            await self.cmd_whoami(update, context)
            return
        if data == "MENU:WALLETS":
            await self.cmd_wallet(update, context)
            return
        if data == "MENU:DEPOSIT":
            await self.cmd_deposit(update, context)
            return
        if data == "MENU:BALANCE":
            await self.cmd_balance(update, context)
            return
        if data == "MENU:STATEMENT":
            await self.cmd_statement(update, context)
            return
        if data == "MENU:SUMMARY":
            await self.cmd_summary(update, context)
            return
        if data == "MENU:REFERRALS":
            await self.cmd_referrals(update, context)
            return
        if data == "MENU:INVEST":
            await self.cmd_invest(update, context)
            return
        if data == "MENU:LINK_BNB":
            context.user_data["state"] = STATE_AWAITING_BNB_ADDRESS
            await q.message.reply_text("שלח עכשיו כתובת BNB (מתחילה ב-0x...)")
            return
        if data == "MENU:ADMIN":
            if not self._is_admin(tg.id):
                await q.message.reply_text("אין הרשאה.")
                return
            await q.message.reply_text("🛠 פאנל אדמין:", reply_markup=self._admin_markup())
            return

        # Admin callbacks
        if not self._is_admin(tg.id):
            return

        if data == "ADMIN:STATUS":
            db = self._db()
            try:
                users = db.query(models.User).count()
                wallets = db.query(models.Wallet).count()
                pending = db.query(models.InvestorProfile).filter(models.InvestorProfile.status == "candidate").count()
                active = db.query(models.InvestorProfile).filter(models.InvestorProfile.status == "active").count()
            finally:
                db.close()
            await q.message.reply_text(
                "📊 סטטוס מערכת\n\n"
                f"משתמשים: {users}\n"
                f"ארנקים: {wallets}\n"
                f"ממתינים לאישור: {pending}\n"
                f"משקיעים פעילים: {active}\n"
            )
            return

        if data == "ADMIN:APPROVE":
            context.user_data["admin_state"] = "AWAIT_APPROVE_ID"
            await q.message.reply_text("שלח Telegram ID לאישור (מספר בלבד).")
            return

        if data == "ADMIN:CREDIT":
            context.user_data["admin_state"] = "AWAIT_CREDIT"
            await q.message.reply_text("שלח: <telegram_id> <amount> [currency]\nדוגמה: 224223270 100 USDT_TON")
            return

        if data == "ADMIN:LEDGER":
            await self.cmd_admin_ledger(update, context)
            return

        if data == "ADMIN:ACCRUE":
            context.user_data["admin_state"] = "AWAIT_ACCRUE"
            await q.message.reply_text("שלח: [apr] [currency] [YYYY-MM-DD]\nדוגמה: 0.18 USDT_TON 2025-12-14\nאו פשוט: 0.18")
            return

        if data == "ADMIN:SELFTEST":
            await self.cmd_admin_selftest(update, context)
            return

    # -------- Text handler --------

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        txt = (update.message.text or "").strip()

        # Admin chat states
        if self._is_admin(update.effective_user.id):
            st = context.user_data.get("admin_state")
            if st == "AWAIT_APPROVE_ID":
                if txt.isdigit():
                    tid = int(txt)
                    db = self._db()
                    try:
                        crud.approve_investor(db, tid)
                        self._ensure_investor_wallet(db, tid)
                    finally:
                        db.close()
                    await update.message.reply_text(f"✅ אושר משקיע: {tid}")
                    context.user_data["admin_state"] = None
                    return
                await update.message.reply_text("נא לשלוח מספר בלבד.")
                return

            if st == "AWAIT_CREDIT":
                parts = txt.split()
                if len(parts) < 2:
                    await update.message.reply_text("שגיאה. שלח: <telegram_id> <amount> [currency]")
                    return
                tid = int(parts[0])
                amt = _parse_decimal(parts[1])
                cur = (parts[2] if len(parts) >= 3 else "USDT_TON").upper()
                db = self._db()
                try:
                    self._ensure_investor_wallet(db, tid)
                    ledger.create_entry(
                        db,
                        telegram_id=tid,
                        wallet_type="investor",
                        direction="in",
                        amount=amt,
                        currency=cur,
                        reason="admin_credit",
                        meta={"by": str(update.effective_user.id)},
                    )
                    bal = ledger.get_balance(db, telegram_id=tid, wallet_type="investor", currency=cur)
                finally:
                    db.close()
                await update.message.reply_text(f"✅ זוכה {tid} ב-{amt} {cur}. יתרה חדשה: {bal}")
                context.user_data["admin_state"] = None
                return

            if st == "AWAIT_ACCRUE":
                parts = txt.split()
                apr = _parse_decimal(parts[0]) if len(parts) >= 1 else _parse_decimal(settings.DEFAULT_APR or "0.18")
                cur = (parts[1] if len(parts) >= 2 else "USDT_TON").upper()
                day = date.fromisoformat(parts[2]) if len(parts) >= 3 else None
                db = self._db()
                try:
                    res = run_daily_interest_accrual(db, apr=apr, currency=cur, wallet_type="investor", accrual_day=day)
                finally:
                    db.close()
                await update.message.reply_text(
                    "📈 ריבית יומית בוצעה\n\n"
                    f"processed={res.processed}\n"
                    f"credited={res.credited}\n"
                    f"skipped={res.skipped}\n"
                    f"total_interest={res.total_interest}\n"
                )
                context.user_data["admin_state"] = None
                return

        # User state: awaiting BNB address
        state = context.user_data.get("state")
        if state == STATE_AWAITING_BNB_ADDRESS:
            context.user_data["state"] = None
            if not (txt.startswith("0x") and len(txt) >= 10):
                await update.message.reply_text("כתובת לא תקינה. נסה שוב: /link_wallet")
                return

            db = self._db()
            try:
                user = crud.get_or_create_user(db, update.effective_user.id, update.effective_user.username)
                crud.set_bnb_address(db, user, txt)
                await update.message.reply_text(f"✅ נשמרה כתובת BNB:\n{txt}")
            finally:
                db.close()
            return

        await update.message.reply_text("לא הבנתי. נסה /menu")


_bot = InvestorWalletBot()


async def initialize_bot():
    await _bot.initialize()


async def process_webhook(update_dict: dict):
    if not _bot.application:
        return
    update = Update.de_json(update_dict, _bot.application.bot)
    await _bot.application.process_update(update)
