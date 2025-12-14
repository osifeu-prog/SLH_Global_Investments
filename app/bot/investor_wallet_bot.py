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
from app import models
from app import crud
from app import ledger
from app.yield_engine import run_daily_interest_accrual

logger = logging.getLogger(__name__)

STATE_AWAITING_BNB_ADDRESS = "AWAITING_BNB_ADDRESS"


def _d(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def _fmt(x: Decimal, nd: int = 8) -> str:
    q = Decimal("1." + ("0" * nd))
    return f"{(x.quantize(q)):f}"


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
                    InlineKeyboardButton("📄 דוח תנועות", callback_data="MENU:STATEMENT"),
                    InlineKeyboardButton("🎁 הפניות", callback_data="MENU:REFERRALS"),
                ],
                [
                    InlineKeyboardButton("📥 בקשת השקעה", callback_data="MENU:INVEST"),
                    InlineKeyboardButton("🔗 קישור כתובת BNB", callback_data="MENU:LINK_BNB"),
                ],
                [
                    InlineKeyboardButton("❓ עזרה", callback_data="MENU:HELP"),
                    InlineKeyboardButton("🛠 אדמין", callback_data="MENU:ADMIN"),
                ],
            ]
        )

    def _admin_markup(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📊 סטטוס מערכת", callback_data="ADMIN:STATUS")],
                [InlineKeyboardButton("✅ אישור משקיע", callback_data="ADMIN:APPROVE")],
                [InlineKeyboardButton("❌ דחיית משקיע", callback_data="ADMIN:REJECT")],
                [InlineKeyboardButton("💳 זיכוי (manual)", callback_data="ADMIN:CREDIT_HELP")],
                [InlineKeyboardButton("🏦 ריבית יומית (run)", callback_data="ADMIN:INTEREST_HELP")],
            ]
        )

    async def initialize(self):
        if not settings.BOT_TOKEN:
            logger.warning("BOT_TOKEN missing, bot disabled")
            return

        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        self._bot_username = (await self.application.bot.get_me()).username

        # Commands
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("menu", self.cmd_menu))
        self.application.add_handler(CommandHandler("help", self.cmd_help))

        self.application.add_handler(CommandHandler("whoami", self.cmd_whoami))
        self.application.add_handler(CommandHandler("wallet", self.cmd_wallet))
        self.application.add_handler(CommandHandler("referrals", self.cmd_referrals))
        self.application.add_handler(CommandHandler("invest", self.cmd_invest))
        self.application.add_handler(CommandHandler("link_wallet", self.cmd_link_wallet))

        # Ledger/user-facing
        self.application.add_handler(CommandHandler("deposit", self.cmd_deposit))
        self.application.add_handler(CommandHandler("balance", self.cmd_balance))
        self.application.add_handler(CommandHandler("statement", self.cmd_statement))

        # Admin
        self.application.add_handler(CommandHandler("admin", self.cmd_admin))
        self.application.add_handler(CommandHandler("admin_credit", self.cmd_admin_credit))
        self.application.add_handler(CommandHandler("admin_debit", self.cmd_admin_debit))
        self.application.add_handler(CommandHandler("admin_run_interest", self.cmd_admin_run_interest))

        # Callback menu
        self.application.add_handler(CallbackQueryHandler(self.cb_menu))

        # Text handler
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

        # Error handler
        self.application.add_error_handler(self.on_error)

        await self.application.initialize()

        # Webhook
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

    def _ledger_wallet_type(self) -> str:
        return (settings.LEDGER_DEFAULT_WALLET_TYPE or "investor").strip()

    def _default_asset(self) -> str:
        return (settings.DEFAULT_DEPOSIT_ASSET or "USDT_TON").strip().upper()

    # -------- Commands --------

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
                            ref_user.slha_balance = (ref_user.slha_balance or Decimal("0")) + Decimal(str(reward))
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
            "/balance – יתרה (ledger)\n"
            "/statement – דוח תנועות\n"
            "/referrals – הפניות\n"
            "/invest – בקשת השקעה\n"
            "/link_wallet – קישור כתובת BNB\n"
        )
        if self._is_admin(update.effective_user.id):
            txt += (
                "\n\nאדמין:\n"
                "/admin\n"
                "/admin_credit <tid> <amount> <currency> [wallet_type] [reason]\n"
                "/admin_debit <tid> <amount> <currency> [wallet_type] [reason]\n"
                "/admin_run_interest [APR] [currency] [wallet_type]\n"
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
                f"SLH (legacy): {Decimal(user.balance_slh or 0):,.6f}\n"
                f"SLHA (נקודות): {Decimal(user.slha_balance or 0):,.8f}\n\n"
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
                    f"- {w.wallet_type.upper()} | "
                    f"סוג: {w.kind} | "
                    f"הפקדות: {'✅' if w.deposits_enabled else '❌'} | "
                    f"משיכות: {'✅' if w.withdrawals_enabled else '❌'} | "
                    f"SLH(legacy): {Decimal(w.balance_slh or 0):,.6f} | "
                    f"SLHA: {Decimal(w.balance_slha or 0):,.8f}"
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
                "להפקדה: /deposit"
            )
        finally:
            db.close()

    # -------- Ledger / money-facing --------

    async def cmd_deposit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Phase 1 (נוח ומהיר): Treasury אחד + Memo/Comment = Telegram ID
        בהמשך נחבר indexer שמזהה on-chain ומייצר ledger IN אוטומטית.
        """
        tg = update.effective_user
        asset = self._default_asset()
        wallet_type = self._ledger_wallet_type()

        ton_addr = settings.TON_TREASURY_ADDRESS or "(חסר TON_TREASURY_ADDRESS)"
        usdt_addr = settings.USDT_TON_TREASURY_ADDRESS or ton_addr or "(חסר USDT_TON_TREASURY_ADDRESS)"

        if asset == "TON":
            addr = ton_addr
            instr = "שלח TON לכתובת הבאה"
        else:
            addr = usdt_addr
            instr = "שלח USDT (על TON) לכתובת הבאה"

        txt = (
            "💰 הפקדה\n\n"
            f"{instr}:\n{addr}\n\n"
            f"חשוב: הוסף Memo/Comment (הערה) = {tg.id}\n"
            "ככה נוכל להצמיד הפקדה למשתמש בצורה חד-משמעית.\n\n"
            f"ארנק יעד במערכת: {wallet_type}\n"
        )
        await update.message.reply_text(txt)

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        wallet_type = self._ledger_wallet_type()

        db = self._db()
        try:
            # מציגים שתי יתרות נפוצות. אפשר להרחיב בהמשך.
            bal_usdt = ledger.get_balance(db, telegram_id=tg.id, wallet_type=wallet_type, currency="USDT_TON")
            bal_ton = ledger.get_balance(db, telegram_id=tg.id, wallet_type=wallet_type, currency="TON")

            txt = (
                "📊 יתרה (Ledger)\n\n"
                f"ארנק: {wallet_type}\n"
                f"USDT_TON: {_fmt(bal_usdt, 8)}\n"
                f"TON: {_fmt(bal_ton, 8)}\n"
            )
            await update.message.reply_text(txt)
        finally:
            db.close()

    async def cmd_statement(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        wallet_type = self._ledger_wallet_type()

        db = self._db()
        try:
            rows = ledger.get_statement(db, telegram_id=tg.id, wallet_type=wallet_type, limit=10)
            if not rows:
                await update.message.reply_text("📄 אין עדיין תנועות.")
                return

            lines = ["📄 דוח תנועות (אחרונות):\n"]
            for r in rows:
                ts = r.created_at.isoformat() if r.created_at else ""
                lines.append(
                    f"- [{ts}] {r.direction.upper()} {r.amount} {r.currency} "
                    f"(reason={r.reason})"
                )

            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    # -------- Admin --------

    async def cmd_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("אין הרשאה.")
            return
        await update.message.reply_text("🛠 פאנל אדמין:", reply_markup=self._admin_markup())

    async def cmd_admin_credit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            return

        parts = (update.message.text or "").split()
        if len(parts) < 4:
            await update.message.reply_text("שימוש: /admin_credit <tid> <amount> <currency> [wallet_type] [reason]")
            return

        tid = int(parts[1])
        amount = _d(parts[2])
        currency = parts[3]
        wallet_type = parts[4] if len(parts) >= 5 else self._ledger_wallet_type()
        reason = parts[5] if len(parts) >= 6 else "manual_credit"

        db = self._db()
        try:
            # ensure user exists
            crud.get_or_create_user(db, tid, None)
            ledger.create_entry(
                db,
                telegram_id=tid,
                wallet_type=wallet_type,
                direction="in",
                amount=amount,
                currency=currency,
                reason=reason,
                meta={"by_admin": str(update.effective_user.id)},
            )
            await update.message.reply_text(f"✅ זיכוי נרשם: tid={tid} +{amount} {currency} ({wallet_type})")
        finally:
            db.close()

    async def cmd_admin_debit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            return

        parts = (update.message.text or "").split()
        if len(parts) < 4:
            await update.message.reply_text("שימוש: /admin_debit <tid> <amount> <currency> [wallet_type] [reason]")
            return

        tid = int(parts[1])
        amount = _d(parts[2])
        currency = parts[3]
        wallet_type = parts[4] if len(parts) >= 5 else self._ledger_wallet_type()
        reason = parts[5] if len(parts) >= 6 else "manual_debit"

        db = self._db()
        try:
            bal = ledger.get_balance(db, telegram_id=tid, wallet_type=wallet_type, currency=currency)
            if bal < amount:
                await update.message.reply_text(f"❌ יתרה לא מספיקה. balance={bal} < {amount}")
                return

            ledger.create_entry(
                db,
                telegram_id=tid,
                wallet_type=wallet_type,
                direction="out",
                amount=amount,
                currency=currency,
                reason=reason,
                meta={"by_admin": str(update.effective_user.id)},
            )
            await update.message.reply_text(f"✅ חיוב נרשם: tid={tid} -{amount} {currency} ({wallet_type})")
        finally:
            db.close()

    async def cmd_admin_run_interest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        ריבית יומית (ריבית-דריבית) לכל משקיע Active:
        שימוש:
          /admin_run_interest [APR] [currency] [wallet_type]
        """
        if not self._is_admin(update.effective_user.id):
            return

        parts = (update.message.text or "").split()
        apr = _d(parts[1]) if len(parts) >= 2 else _d(settings.DEFAULT_APR or "0")
        currency = parts[2].upper() if len(parts) >= 3 else "USDT_TON"
        wallet_type = parts[3] if len(parts) >= 4 else self._ledger_wallet_type()

        db = self._db()
        try:
            res = run_daily_interest_accrual(
                db,
                apr=apr,
                currency=currency,
                wallet_type=wallet_type,
                accrual_day=date.today(),
            )
            await update.message.reply_text(
                "🏦 ריבית יומית בוצעה\n\n"
                f"APR: {apr}\n"
                f"Currency: {currency}\n"
                f"Wallet: {wallet_type}\n\n"
                f"Processed: {res.processed}\n"
                f"Credited: {res.credited}\n"
                f"Skipped: {res.skipped}\n"
                f"Total interest: {res.total_interest}\n"
            )
        finally:
            db.close()

    # -------- Callback menu --------

    async def cb_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        data = q.data or ""
        tg = update.effective_user

        if data == "MENU:WHOAMI":
            await self.cmd_whoami(_fake_update(update, q.message), context)
            return
        if data == "MENU:WALLETS":
            await self.cmd_wallet(_fake_update(update, q.message), context)
            return
        if data == "MENU:REFERRALS":
            await self.cmd_referrals(_fake_update(update, q.message), context)
            return
        if data == "MENU:INVEST":
            await self.cmd_invest(_fake_update(update, q.message), context)
            return
        if data == "MENU:LINK_BNB":
            context.user_data["state"] = STATE_AWAITING_BNB_ADDRESS
            await q.message.reply_text("שלח עכשיו כתובת BNB (מתחילה ב-0x...)")
            return
        if data == "MENU:HELP":
            await q.message.reply_text("נסה /help או /menu")
            return
        if data == "MENU:DEPOSIT":
            await self.cmd_deposit(_fake_update(update, q.message), context)
            return
        if data == "MENU:BALANCE":
            await self.cmd_balance(_fake_update(update, q.message), context)
            return
        if data == "MENU:STATEMENT":
            await self.cmd_statement(_fake_update(update, q.message), context)
            return
        if data == "MENU:ADMIN":
            if not self._is_admin(tg.id):
                await q.message.reply_text("אין הרשאה.")
                return
            await q.message.reply_text("🛠 פאנל אדמין:", reply_markup=self._admin_markup())
            return

        # Admin callbacks
        if data == "ADMIN:STATUS":
            if not self._is_admin(tg.id):
                return
            db = self._db()
            try:
                users = db.query(models.User).count()
                wallets = db.query(models.Wallet).count()
                pending = db.query(models.InvestorProfile).filter(models.InvestorProfile.status == "candidate").count()
                active = db.query(models.InvestorProfile).filter(models.InvestorProfile.status.in_(["active", "approved"])).count()
                txt = (
                    "📊 סטטוס מערכת\n\n"
                    f"משתמשים: {users}\n"
                    f"ארנקים: {wallets}\n"
                    f"ממתינים לאישור: {pending}\n"
                    f"משקיעים פעילים: {active}\n"
                )
            finally:
                db.close()
            await q.message.reply_text(txt)
            return

        if data == "ADMIN:APPROVE":
            if not self._is_admin(tg.id):
                return
            context.user_data["admin_state"] = "AWAIT_APPROVE_ID"
            await q.message.reply_text("שלח Telegram ID לאישור (מספר בלבד).")
            return

        if data == "ADMIN:REJECT":
            if not self._is_admin(tg.id):
                return
            context.user_data["admin_state"] = "AWAIT_REJECT_ID"
            await q.message.reply_text("שלח Telegram ID לדחייה (מספר בלבד).")
            return

        if data == "ADMIN:CREDIT_HELP":
            await q.message.reply_text(
                "💳 זיכוי/חיוב ידני (לשלב ראשון):\n\n"
                "/admin_credit <tid> <amount> <currency> [wallet_type] [reason]\n"
                "/admin_debit <tid> <amount> <currency> [wallet_type] [reason]\n\n"
                "דוגמה:\n"
                "/admin_credit 224223270 100 USDT_TON investor deposit_manual"
            )
            return

        if data == "ADMIN:INTEREST_HELP":
            await q.message.reply_text(
                "🏦 ריבית יומית (ריבית-דריבית):\n\n"
                "/admin_run_interest [APR] [currency] [wallet_type]\n\n"
                "דוגמה:\n"
                "/admin_run_interest 0.18 USDT_TON investor"
            )
            return

    # -------- Text handler --------

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (update.message.text or "").strip()

        # Admin state
        admin_state = context.user_data.get("admin_state")
        if admin_state and self._is_admin(update.effective_user.id):
            if text.isdigit():
                target = int(text)
                db = self._db()
                try:
                    if admin_state == "AWAIT_APPROVE_ID":
                        crud.approve_investor(db, target)
                        self._ensure_investor_wallet(db, target)
                        await update.message.reply_text(f"✅ אושר משקיע: {target}")
                    elif admin_state == "AWAIT_REJECT_ID":
                        crud.reject_investor(db, target)
                        await update.message.reply_text(f"❌ נדחה משקיע: {target}")
                finally:
                    db.close()
                context.user_data["admin_state"] = None
            else:
                await update.message.reply_text("נא לשלוח מספר בלבד.")
            return

        # User state: awaiting BNB address
        state = context.user_data.get("state")
        if state == STATE_AWAITING_BNB_ADDRESS:
            context.user_data["state"] = None
            if not (text.startswith("0x") and len(text) >= 10):
                await update.message.reply_text("כתובת לא תקינה. נסה שוב: /link_wallet")
                return

            db = self._db()
            try:
                user = crud.get_or_create_user(db, update.effective_user.id, update.effective_user.username)
                crud.set_bnb_address(db, user, text)
                await update.message.reply_text(f"✅ נשמרה כתובת BNB:\n{text}")
            finally:
                db.close()
            return

        await update.message.reply_text("לא הבנתי. נסה /menu")


class _fake_update(Update):
    """Helper to reuse command handlers for callback queries."""
    def __init__(self, original: Update, message):
        super().__init__(update_id=original.update_id)
        self._effective_user = original.effective_user
        self._message = message

    @property
    def effective_user(self):
        return self._effective_user

    @property
    def message(self):
        return self._message


_bot = InvestorWalletBot()


async def initialize_bot():
    await _bot.initialize()


async def process_webhook(update_dict: dict):
    if not _bot.application:
        return
    update = Update.de_json(update_dict, _bot.application.bot)
    await _bot.application.process_update(update)
