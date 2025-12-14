# app/bot/investor_wallet_bot.py
from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

STATE_AWAITING_BNB_ADDRESS = "AWAITING_BNB_ADDRESS"


def _dec(x) -> Decimal:
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


class InvestorWalletBot:
    def __init__(self):
        self.application: Application | None = None
        self._bot_username: str | None = None

    def _db(self):
        return SessionLocal()

    def _is_admin(self, telegram_id: int) -> bool:
        return bool(settings.ADMIN_USER_ID) and str(telegram_id) == str(settings.ADMIN_USER_ID)

    # -------- UI --------

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
        self.application.add_handler(CommandHandler("deposit", self.cmd_deposit))
        self.application.add_handler(CommandHandler("balance", self.cmd_balance))
        self.application.add_handler(CommandHandler("statement", self.cmd_statement))
        self.application.add_handler(CommandHandler("transfer", self.cmd_transfer))
        self.application.add_handler(CommandHandler("redeem", self.cmd_redeem))
        self.application.add_handler(CommandHandler("admin_redemptions", self.cmd_admin_redemptions))
        self.application.add_handler(CommandHandler("admin_approve_redeem", self.cmd_admin_approve_redeem))
        self.application.add_handler(CommandHandler("admin_reject_redeem", self.cmd_admin_reject_redeem))
        self.application.add_handler(CommandHandler("admin", self.cmd_admin))

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

    def _ensure_investor_wallet_if_needed(self, db, telegram_id: int):
        # only if they started onboarding (or active)
        prof = crud.get_investor_profile(db, telegram_id)
        if prof and str(prof.status).lower() in ("candidate", "active", "approved"):
            crud.get_or_create_wallet(
                db,
                telegram_id=telegram_id,
                wallet_type="investor",
                kind="investor",
                deposits_enabled=True,
                withdrawals_enabled=False,
            )

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
            "/referrals – הפניות\n"
            "/invest – בקשת השקעה\n"
            "/link_wallet – קישור כתובת BNB\n"
            "/transfer – העברת SLHA למשתמש\n"
            "/redeem – בקשת פדיון SLHA\n"
        )
        if self._is_admin(update.effective_user.id):
            txt += "\n/admin – פאנל אדמין"
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
            self._ensure_investor_wallet_if_needed(db, tg.id)

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

            # if came through referral - attach
            ref = (
                db.query(models.Referral)
                .filter(models.Referral.referred_tid == tg.id)
                .order_by(models.Referral.id.desc())
                .first()
            )
            referrer_tid = ref.referrer_tid if ref else None

            crud.start_invest_onboarding(
                db,
                tg.id,
                referrer_tid=referrer_tid,
                note="Requested via bot",
            )

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

        # deposit target wallet_type
        wallet_type = "investor" if crud.is_investor_active(self._db(), tg.id) else "investor"

        txt = (
            "💰 הפקדה\n\n"
            f"שלח {('USDT (על TON)' if asset == 'USDT_TON' else 'TON')} לכתובת הבאה:\n"
            f"{addr}\n\n"
            f"חשוב: הוסף Memo/Comment (הערה) = {tg.id}\n"
            "ככה נוכל להצמיד הפקדה למשתמש בצורה חד-משמעית.\n\n"
            f"ארנק יעד במערכת: {wallet_type}\n"
        )
        await update.message.reply_text(txt)

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            # show internal balances from ledger (ILS/USDT_TON/Ton etc)
            # We’ll start with USDT_TON as accounting anchor.
            usdt = crud.get_ledger_balance(db, telegram_id=tg.id, wallet_type="investor", currency="USDT_TON")
            ton = crud.get_ledger_balance(db, telegram_id=tg.id, wallet_type="investor", currency="TON")

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
            rows = crud.list_ledger_entries(db, telegram_id=tg.id, wallet_type="investor", limit=15)
            if not rows:
                await update.message.reply_text("🧾 אין תנועות עדיין.")
                return

            lines = ["🧾 דוח תנועות (15 אחרונות)\n"]
            for r in rows:
                lines.append(
                    f"- #{r.id} | {r.created_at} | {r.direction.upper()} | {r.amount} {r.currency} | {r.reason}"
                )
            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    async def cmd_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("אין הרשאה.")
            return
        await update.message.reply_text("🛠 פאנל אדמין:", reply_markup=self._admin_markup())

    # -------- Callback menu (NO fake updates) --------

    async def cb_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        data = q.data or ""
        tg = update.effective_user

        # route to "message-based" helpers
        if data == "MENU:WHOAMI":
            await self._whoami_to_message(q.message, tg.id, tg.username)
            return
        if data == "MENU:WALLETS":
            await self._wallets_to_message(q.message, tg.id)
            return
        if data == "MENU:DEPOSIT":
            await self._deposit_to_message(q.message, tg.id)
            return
        if data == "MENU:BALANCE":
            await self._balance_to_message(q.message, tg.id)
            return
        if data == "MENU:STATEMENT":
            await self._statement_to_message(q.message, tg.id)
            return
        if data == "MENU:REFERRALS":
            await self._referrals_to_message(q.message, tg.id)
            return
        if data == "MENU:INVEST":
            await self._invest_to_message(q.message, tg.id)
            return
        if data == "MENU:LINK_BNB":
            context.user_data["state"] = STATE_AWAITING_BNB_ADDRESS
            await q.message.reply_text("שלח עכשיו כתובת BNB (מתחילה ב-0x...)")
            return
        if data == "MENU:HELP":
            await q.message.reply_text("נסה /help או /menu")
            return
        if data == "MENU:ADMIN":
            if not self._is_admin(tg.id):
                await q.message.reply_text("אין הרשאה.")
                return
            await q.message.reply_text("🛠 פאנל אדמין:", reply_markup=self._admin_markup())
            return

        # admin actions
        if data == "ADMIN:STATUS":
            if not self._is_admin(tg.id):
                return
            db = self._db()
            try:
                users = db.query(models.User).count()
                wallets = db.query(models.Wallet).count()
                pending = db.query(models.InvestorProfile).filter(models.InvestorProfile.status == "candidate").count()
                active = db.query(models.InvestorProfile).filter(models.InvestorProfile.status == "active").count()
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

    # ---- helper replies ----

    async def _whoami_to_message(self, message, telegram_id: int, username: Optional[str]):
        db = self._db()
        try:
            user = crud.get_or_create_user(db, telegram_id, username)
            prof = crud.get_investor_profile(db, telegram_id)
            status = "אין" if not prof else str(prof.status)
            txt = (
                "👤 פרופיל\n\n"
                f"ID: {telegram_id}\n"
                f"שם משתמש: @{username}\n"
                f"BNB: {user.bnb_address or 'לא מחובר'}\n"
                f"SLH (פנימי): {_dec(user.balance_slh):,.6f}\n"
                f"SLHA (נקודות): {_dec(user.slha_balance):,.8f}\n\n"
                f"סטטוס משקיע: {status}\n"
            )
            await message.reply_text(txt)
        finally:
            db.close()

    async def _wallets_to_message(self, message, telegram_id: int):
        db = self._db()
        try:
            self._ensure_base_wallet(db, telegram_id)
            self._ensure_investor_wallet_if_needed(db, telegram_id)
            wallets = (
                db.query(models.Wallet)
                .filter(models.Wallet.telegram_id == telegram_id)
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
            await message.reply_text("\n".join(lines))
        finally:
            db.close()

    async def _deposit_to_message(self, message, telegram_id: int):
        asset = (settings.DEFAULT_DEPOSIT_ASSET or "USDT_TON").upper()
        addr = settings.USDT_TON_TREASURY_ADDRESS if asset == "USDT_TON" else settings.TON_TREASURY_ADDRESS
        addr = addr or settings.TON_TREASURY_ADDRESS or "MISSING_TREASURY_ADDRESS"
        txt = (
            "💰 הפקדה\n\n"
            f"שלח {('USDT (על TON)' if asset == 'USDT_TON' else 'TON')} לכתובת הבאה:\n"
            f"{addr}\n\n"
            f"חשוב: הוסף Memo/Comment (הערה) = {telegram_id}\n"
            "ככה נוכל להצמיד הפקדה למשתמש בצורה חד-משמעית.\n\n"
            "ארנק יעד במערכת: investor\n"
        )
        await message.reply_text(txt)

    async def _balance_to_message(self, message, telegram_id: int):
        db = self._db()
        try:
            usdt = crud.get_ledger_balance(db, telegram_id=telegram_id, wallet_type="investor", currency="USDT_TON")
            ton = crud.get_ledger_balance(db, telegram_id=telegram_id, wallet_type="investor", currency="TON")
            txt = (
                "📊 יתרה (לפי Ledger פנימי)\n\n"
                f"USDT_TON: {usdt:,.6f}\n"
                f"TON: {ton:,.6f}\n"
            )
            await message.reply_text(txt)
        finally:
            db.close()

    async def _statement_to_message(self, message, telegram_id: int):
        db = self._db()
        try:
            rows = crud.list_ledger_entries(db, telegram_id=telegram_id, wallet_type="investor", limit=15)
            if not rows:
                await message.reply_text("🧾 אין תנועות עדיין.")
                return
            lines = ["🧾 דוח תנועות (15 אחרונות)\n"]
            for r in rows:
                lines.append(
                    f"- #{r.id} | {r.created_at} | {r.direction.upper()} | {r.amount} {r.currency} | {r.reason}"
                )
            await message.reply_text("\n".join(lines))
        finally:
            db.close()

    async def _referrals_to_message(self, message, telegram_id: int):
        db = self._db()
        try:
            count = crud.count_referrals(db, telegram_id)
            bot_username = self._bot_username or "YOUR_BOT"
            link = f"https://t.me/{bot_username}?start=ref_{telegram_id}"
            txt = (
                "🎁 תוכנית הפניות\n\n"
                f"קישור אישי:\n{link}\n\n"
                f"מספר הפניות: {count}\n"
            )
            await message.reply_text(txt)
        finally:
            db.close()

    async def _invest_to_message(self, message, telegram_id: int):
        db = self._db()
        try:
            self._ensure_base_wallet(db, telegram_id)

            if crud.is_investor_active(db, telegram_id):
                await message.reply_text("✅ כבר יש לך סטטוס משקיע פעיל.")
                return

            ref = (
                db.query(models.Referral)
                .filter(models.Referral.referred_tid == telegram_id)
                .order_by(models.Referral.id.desc())
                .first()
            )
            referrer_tid = ref.referrer_tid if ref else None

            crud.start_invest_onboarding(db, telegram_id, referrer_tid=referrer_tid, note="Requested via bot")

            await message.reply_text(
                "📥 בקשת השקעה נשלחה.\n\n"
                "נפתח לך ארנק משקיע (הפקדות בלבד).\n"
                "לאחר אישור אדמין – הסטטוס יעודכן.\n"
            )
        finally:
            db.close()

    # -------- Text handler --------

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        txt = (update.message.text or "").strip()

        # Admin flow
        admin_state = context.user_data.get("admin_state")
        if admin_state and self._is_admin(update.effective_user.id):
            if txt.isdigit():
                target = int(txt)
                db = self._db()
                try:
                    if admin_state == "AWAIT_APPROVE_ID":
                        crud.approve_investor(db, target)
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



    # ---- Stage 2: Transfers + Redemption ----

    async def cmd_transfer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        args = context.args or []
        if len(args) < 2:
            await update.message.reply_text("שימוש: /transfer <telegram_id> <amount>\nדוגמה: /transfer 123456789 10")
            return
        try:
            to_tid = int(args[0])
            amount = Decimal(str(args[1]))
        except Exception:
            await update.message.reply_text("❌ פרמטרים לא תקינים. שימוש: /transfer <telegram_id> <amount>")
            return

        db = self._db()
        try:
            # ensure accounts exist
            crud.get_or_create_user(db, telegram_id=tg.id, username=tg.username)
            crud.get_or_create_user(db, telegram_id=to_tid, username=None)
            self._ensure_investor_wallet_if_needed(db, tg.id)
            self._ensure_investor_wallet_if_needed(db, to_tid)

            row = crud.transfer_slha(db, from_tid=tg.id, to_tid=to_tid, amount=amount)
            await update.message.reply_text(f"✅ הועברו {row.amount} SLHA למשתמש {to_tid}.")
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
        except Exception:
            logger.exception("transfer failed")
            await update.message.reply_text("⚠️ תקלה בהעברה. נסה שוב מאוחר יותר.")
        finally:
            db.close()

    async def cmd_redeem(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        args = context.args or []
        if not args:
            await update.message.reply_text("שימוש: /redeem <amount> [regular|early] [payout_address(optional)]")
            return
        try:
            amount = Decimal(str(args[0]))
        except Exception:
            await update.message.reply_text("❌ סכום לא תקין.")
            return
        policy = (args[1].lower().strip() if len(args) >= 2 else "regular")
        if policy not in ("regular", "early"):
            policy = "regular"
        payout_address = (args[2].strip() if len(args) >= 3 else None)

        db = self._db()
        try:
            prof = crud.get_investor_profile(db, tg.id)
            cohort = "standard"
            if prof and str(prof.status).lower() in ("candidate", "pending"):
                cohort = "new"

            row = crud.create_redemption_request(
                db,
                telegram_id=tg.id,
                amount_slha=amount,
                cohort=cohort,
                policy=policy,
                payout_address=payout_address,
                note=None,
            )
            await update.message.reply_text(f"✅ בקשת פדיון נרשמה.\nמספר בקשה: #{row.id}\nסכום: {row.amount_slha} SLHA\nמדיניות: {row.policy}\nהבקשה ממתינה לאישור אדמין.")
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
        except Exception:
            logger.exception("redeem failed")
            await update.message.reply_text("⚠️ תקלה בבקשת פדיון. נסה שוב מאוחר יותר.")
        finally:
            db.close()

    

async def cmd_admin_redemptions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    if not self._is_admin(tg.id):
        await update.message.reply_text("אין הרשאה.")
        return

    status = (context.args[0].lower().strip() if context.args else "pending")

    db = self._db()
    try:
        rows = crud.list_redemption_requests(db, status=status, limit=20)
        if not rows:
            await update.message.reply_text(f"🗂 אין בקשות פדיון בסטטוס: {status}")
            return

        lines = [f"🗂 בקשות פדיון (status={status})\n"]
        for r in rows:
            lines.append(f"- #{r.id} | tid={r.telegram_id} | {r.amount_slha} SLHA | policy={r.policy} | cohort={r.cohort}")

        lines.append("\nאישור: /admin_approve_redeem <id>\nדחייה: /admin_reject_redeem <id> [note]")
        await update.message.reply_text("\n".join(lines))
    finally:
        db.close()

async def cmd_admin_approve_redeem(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    if not self._is_admin(tg.id):
        await update.message.reply_text("אין הרשאה.")
        return
    if not context.args:
        await update.message.reply_text("שימוש: /admin_approve_redeem <id>")
        return
    try:
        req_id = int(context.args[0])
    except Exception:
        await update.message.reply_text("❌ id לא תקין.")
        return

    db = self._db()
    try:
        row = db.query(models.RedemptionRequest).filter(models.RedemptionRequest.id == req_id).first()
        if not row:
            await update.message.reply_text("לא נמצאה בקשה.")
            return
        if row.status != "pending":
            await update.message.reply_text(f"⚠️ הבקשה כבר בסטטוס {row.status}.")
            return

        row.status = "approved"
        db.add(row)
        db.commit()
        await update.message.reply_text(f"✅ אושרה בקשת פדיון #{row.id} (tid={row.telegram_id}, {row.amount_slha} SLHA).")
    except Exception:
        logger.exception("approve redeem failed")
        await update.message.reply_text("⚠️ תקלה באישור.")
    finally:
        db.close()

    async def cmd_admin_reject_redeem(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        if not self._is_admin(tg.id):
            await update.message.reply_text("אין הרשאה.")
            return
        if not context.args:
            await update.message.reply_text("שימוש: /admin_reject_redeem <id> [note]")
            return
        try:
            req_id = int(context.args[0])
        except Exception:
            await update.message.reply_text("❌ id לא תקין.")
            return
        note = " ".join(context.args[1:]).strip() if len(context.args) > 1 else None

        db = self._db()
        try:
            row = db.query(models.RedemptionRequest).filter(models.RedemptionRequest.id == req_id).first()
            if not row:
                await update.message.reply_text("לא נמצאה בקשה.")
                return
            if row.status != "pending":
                await update.message.reply_text(f"⚠️ הבקשה כבר בסטטוס {row.status}.")
                return

            # unlock points back to user
            ledger.create_entry(
                db,
                telegram_id=int(row.telegram_id),
                wallet_type="investor",
                direction="in",
                amount=Decimal(str(row.amount_slha)),
                currency="SLHA",
                reason="redeem_unlock",
                meta={"req_id": row.id},
            )

            row.status = "rejected"
            if note:
                row.note = note
            db.add(row)
            db.commit()
            await update.message.reply_text(f"✅ נדחתה בקשת פדיון #{row.id}. הנקודות שוחררו חזרה למשקיע.")
        except Exception:
            logger.exception("reject redeem failed")
            await update.message.reply_text("⚠️ תקלה בדחייה.")
        finally:
            db.close()
