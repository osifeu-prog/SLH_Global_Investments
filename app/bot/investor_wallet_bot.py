# app/bot/investor_wallet_bot.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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

logger = logging.getLogger(__name__)

STATE_AWAITING_BNB_ADDRESS = "AWAITING_BNB_ADDRESS"


# =========================
# DB helpers (self-contained)
# =========================

def _utcnow():
    return datetime.now(timezone.utc)


def db_get_or_create_user(db, telegram_id: int, username: Optional[str] = None) -> models.User:
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    if user:
        if username is not None and user.username != username:
            user.username = username
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    user = models.User(
        telegram_id=telegram_id,
        username=username,
        balance_slh=Decimal("0"),
        slha_balance=Decimal("0"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def db_get_wallet(db, telegram_id: int, wallet_type: str) -> Optional[models.Wallet]:
    return (
        db.query(models.Wallet)
        .filter(models.Wallet.telegram_id == telegram_id, models.Wallet.wallet_type == wallet_type)
        .first()
    )


def db_get_or_create_wallet(
    db,
    telegram_id: int,
    wallet_type: str,
    *,
    kind: str,
    deposits_enabled: bool,
    withdrawals_enabled: bool,
) -> models.Wallet:
    w = db_get_wallet(db, telegram_id, wallet_type)
    if w:
        w.kind = kind
        w.deposits_enabled = deposits_enabled
        w.withdrawals_enabled = withdrawals_enabled

        # keep NOT NULL columns safe
        if w.is_active is None:
            w.is_active = True
        if w.balance_slh is None:
            w.balance_slh = Decimal("0")
        if w.balance_slha is None:
            w.balance_slha = Decimal("0")

        db.add(w)
        db.commit()
        db.refresh(w)
        return w

    w = models.Wallet(
        telegram_id=telegram_id,
        wallet_type=wallet_type,     # NOT NULL
        is_active=True,              # NOT NULL
        balance_slh=Decimal("0"),    # NOT NULL
        balance_slha=Decimal("0"),   # NOT NULL
        kind=kind,
        deposits_enabled=deposits_enabled,
        withdrawals_enabled=withdrawals_enabled,
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


def db_set_bnb_address(db, user: models.User, addr: str) -> None:
    user.bnb_address = addr
    db.add(user)
    db.commit()
    db.refresh(user)


def db_count_referrals(db, telegram_id: int) -> int:
    return db.query(models.Referral).filter(models.Referral.referrer_tid == telegram_id).count()


def db_apply_referral(db, referrer_tid: int, referred_tid: int) -> bool:
    """Create referral row only once. Returns True if created."""
    if referrer_tid == referred_tid:
        return False

    exists = (
        db.query(models.Referral)
        .filter(models.Referral.referrer_tid == referrer_tid, models.Referral.referred_tid == referred_tid)
        .first()
    )
    if exists:
        return False

    row = models.Referral(referrer_tid=referrer_tid, referred_tid=referred_tid)
    db.add(row)
    db.commit()
    return True


def db_get_investor_profile(db, telegram_id: int) -> Optional[models.InvestorProfile]:
    return (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )


def db_is_investor_active(db, telegram_id: int) -> bool:
    prof = db_get_investor_profile(db, telegram_id)
    if not prof:
        return False
    return str(prof.status).lower() in ("active", "approved")


def db_start_invest_onboarding(
    db,
    telegram_id: int,
    *,
    referrer_tid: Optional[int] = None,
    note: Optional[str] = None,
) -> models.InvestorProfile:
    prof = db_get_investor_profile(db, telegram_id)
    if prof:
        prof.status = "candidate"
        # keep safe / not null
        if getattr(prof, "risk_ack", None) is None:
            prof.risk_ack = False
        if referrer_tid is not None:
            prof.referrer_tid = referrer_tid
        if note is not None:
            prof.note = note
        db.add(prof)
        db.commit()
        db.refresh(prof)
    else:
        prof = models.InvestorProfile(
            telegram_id=telegram_id,
            status="candidate",       # REQUIRED (DB)
            risk_ack=False,           # REQUIRED (DB)
            referrer_tid=referrer_tid,
            note=note,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(prof)
        db.commit()
        db.refresh(prof)

    # ensure investor wallet exists (deposits only)
    db_get_or_create_wallet(
        db,
        telegram_id=telegram_id,
        wallet_type="investor",
        kind="investor",
        deposits_enabled=True,
        withdrawals_enabled=False,
    )
    return prof


def db_approve_investor(db, telegram_id: int) -> models.InvestorProfile:
    prof = db_get_investor_profile(db, telegram_id)
    if not prof:
        prof = db_start_invest_onboarding(db, telegram_id, note="Auto-created on approve")

    prof.status = "active"
    prof.approved_at = _utcnow()
    if prof.risk_ack is None:
        prof.risk_ack = False

    db.add(prof)
    db.commit()
    db.refresh(prof)

    # ensure wallet exists
    db_get_or_create_wallet(
        db,
        telegram_id=telegram_id,
        wallet_type="investor",
        kind="investor",
        deposits_enabled=True,
        withdrawals_enabled=False,
    )
    return prof


def db_reject_investor(db, telegram_id: int) -> models.InvestorProfile:
    prof = db_get_investor_profile(db, telegram_id)
    if not prof:
        prof = db_start_invest_onboarding(db, telegram_id, note="Auto-created on reject")

    prof.status = "rejected"
    if prof.risk_ack is None:
        prof.risk_ack = False

    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


# =========================
# Bot implementation
# =========================

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
                    InlineKeyboardButton("🎁 הפניות", callback_data="MENU:REFERRALS"),
                    InlineKeyboardButton("📥 השקעה", callback_data="MENU:INVEST"),
                ],
                [
                    InlineKeyboardButton("🔗 קישור כתובת BNB", callback_data="MENU:LINK_BNB"),
                    InlineKeyboardButton("❓ עזרה", callback_data="MENU:HELP"),
                ],
            ]
        )

    def _admin_markup(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📊 סטטוס מערכת", callback_data="ADMIN:STATUS")],
                [InlineKeyboardButton("✅ לאשר משקיע (לפי ID)", callback_data="ADMIN:APPROVE")],
                [InlineKeyboardButton("❌ לדחות משקיע (לפי ID)", callback_data="ADMIN:REJECT")],
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
        self.application.add_handler(CommandHandler("whoami", self.cmd_whoami))
        self.application.add_handler(CommandHandler("wallet", self.cmd_wallet))
        self.application.add_handler(CommandHandler("referrals", self.cmd_referrals))
        self.application.add_handler(CommandHandler("invest", self.cmd_invest))
        self.application.add_handler(CommandHandler("link_wallet", self.cmd_link_wallet))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("admin", self.cmd_admin))

        # Admin commands (optional)
        self.application.add_handler(CommandHandler("admin_approve_investor", self.cmd_admin_approve_investor))
        self.application.add_handler(CommandHandler("admin_reject_investor", self.cmd_admin_reject_investor))

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
            if isinstance(update, Update) and update.effective_message:
                await update.effective_message.reply_text("⚠️ תקלה זמנית. נסה שוב /menu")
        except Exception:
            pass

    # --------- internal ensures ---------

    def _ensure_base_wallet(self, db, telegram_id: int):
        db_get_or_create_wallet(
            db,
            telegram_id=telegram_id,
            wallet_type="base",
            kind="base",
            deposits_enabled=True,
            withdrawals_enabled=False,
        )

    # --------- "send" helpers (used by both commands & callbacks) ---------

    async def _send_whoami(self, chat_message, tg_user):
        db = self._db()
        try:
            user = db_get_or_create_user(db, tg_user.id, tg_user.username)
            prof = db_get_investor_profile(db, tg_user.id)
            status = str(prof.status) if prof else "אין"

            txt = (
                "👤 פרופיל\n\n"
                f"ID: {tg_user.id}\n"
                f"שם משתמש: @{tg_user.username}\n"
                f"BNB: {user.bnb_address or 'לא מחובר'}\n"
                f"SLH (פנימי): {Decimal(user.balance_slh or 0):,.6f}\n"
                f"SLHA (נקודות): {Decimal(user.slha_balance or 0):,.8f}\n\n"
                f"סטטוס משקיע: {status}\n"
            )
            await chat_message.reply_text(txt)
        finally:
            db.close()

    async def _send_wallets(self, chat_message, tg_user):
        db = self._db()
        try:
            self._ensure_base_wallet(db, tg_user.id)

            wallets = (
                db.query(models.Wallet)
                .filter(models.Wallet.telegram_id == tg_user.id)
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
                    f"SLH: {Decimal(w.balance_slh or 0):,.6f} | "
                    f"SLHA: {Decimal(w.balance_slha or 0):,.8f}"
                )

            await chat_message.reply_text("\n".join(lines))
        finally:
            db.close()

    async def _send_referrals(self, chat_message, tg_user):
        db = self._db()
        try:
            count = db_count_referrals(db, tg_user.id)
            bot_username = self._bot_username or "YOUR_BOT"
            link = f"https://t.me/{bot_username}?start=ref_{tg_user.id}"

            txt = (
                "🎁 תוכנית הפניות\n\n"
                f"קישור אישי:\n{link}\n\n"
                f"מספר הפניות: {count}\n"
            )
            await chat_message.reply_text(txt)
        finally:
            db.close()

    async def _send_invest(self, chat_message, tg_user):
        db = self._db()
        try:
            self._ensure_base_wallet(db, tg_user.id)

            if db_is_investor_active(db, tg_user.id):
                await chat_message.reply_text("✅ כבר יש לך סטטוס משקיע פעיל.")
                return

            # find referrer if exists
            ref = (
                db.query(models.Referral)
                .filter(models.Referral.referred_tid == tg_user.id)
                .order_by(models.Referral.id.desc())
                .first()
            )
            referrer_tid = ref.referrer_tid if ref else None

            db_start_invest_onboarding(
                db,
                tg_user.id,
                referrer_tid=referrer_tid,
                note="Requested via bot",
            )

            await chat_message.reply_text(
                "📥 בקשת השקעה נשלחה.\n\n"
                "נפתח לך ארנק משקיע (הפקדות בלבד).\n"
                "לאחר אישור אדמין – הסטטוס יעודכן ותיפתח גישה מלאה.\n\n"
                "אם אתה אדמין: השתמש ב־/admin"
            )
        finally:
            db.close()

    # --------- Commands ---------

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        start_payload = (context.args[0] if context.args else None)

        db = self._db()
        try:
            db_get_or_create_user(db, tg.id, tg.username)
            self._ensure_base_wallet(db, tg.id)

            # referral capture: /start ref_<id>
            if start_payload and start_payload.startswith("ref_"):
                try:
                    referrer_tid = int(start_payload.replace("ref_", "").strip())
                    created = db_apply_referral(db, referrer_tid, tg.id)
                    if created:
                        reward = getattr(settings, "SLHA_REWARD_REFERRAL", None)
                        if reward:
                            ref_user = db_get_or_create_user(db, referrer_tid, None)
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
        await update.message.reply_text(
            "פקודות:\n"
            "/menu – תפריט\n"
            "/whoami – פרופיל\n"
            "/wallet – ארנקים\n"
            "/referrals – הפניות\n"
            "/invest – בקשת השקעה\n"
            "/link_wallet – קישור כתובת BNB\n"
            + ("\n/admin – פאנל אדמין" if self._is_admin(update.effective_user.id) else "")
        )

    async def cmd_whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._send_whoami(update.message, update.effective_user)

    async def cmd_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._send_wallets(update.message, update.effective_user)

    async def cmd_referrals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._send_referrals(update.message, update.effective_user)

    async def cmd_link_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data["state"] = STATE_AWAITING_BNB_ADDRESS
        await update.message.reply_text("שלח עכשיו כתובת BNB (מתחילה ב-0x...)")

    async def cmd_invest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._send_invest(update.message, update.effective_user)

    async def cmd_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("אין הרשאה.")
            return
        await update.message.reply_text("🛠 פאנל אדמין:", reply_markup=self._admin_markup())

    async def cmd_admin_approve_investor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            return
        parts = update.message.text.split()
        if len(parts) < 2:
            await update.message.reply_text("שימוש: /admin_approve_investor <telegram_id>")
            return
        target = int(parts[1])
        db = self._db()
        try:
            db_approve_investor(db, target)
            await update.message.reply_text(f"✅ אושר משקיע: {target}")
        finally:
            db.close()

    async def cmd_admin_reject_investor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            return
        parts = update.message.text.split()
        if len(parts) < 2:
            await update.message.reply_text("שימוש: /admin_reject_investor <telegram_id>")
            return
        target = int(parts[1])
        db = self._db()
        try:
            db_reject_investor(db, target)
            await update.message.reply_text(f"❌ נדחה משקיע: {target}")
        finally:
            db.close()

    # --------- Callback menu (NO Fake Update) ---------

    async def cb_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()

        data = q.data or ""
        tg = update.effective_user
        msg = q.message  # this is a Message – reply on it

        if data == "MENU:WHOAMI":
            await self._send_whoami(msg, tg)
            return

        if data == "MENU:WALLETS":
            await self._send_wallets(msg, tg)
            return

        if data == "MENU:REFERRALS":
            await self._send_referrals(msg, tg)
            return

        if data == "MENU:INVEST":
            await self._send_invest(msg, tg)
            return

        if data == "MENU:LINK_BNB":
            context.user_data["state"] = STATE_AWAITING_BNB_ADDRESS
            await msg.reply_text("שלח עכשיו כתובת BNB (מתחילה ב-0x...)")
            return

        if data == "MENU:HELP":
            await msg.reply_text("נסה /menu או /help")
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
            await msg.reply_text(txt)
            return

        if data == "ADMIN:APPROVE":
            if not self._is_admin(tg.id):
                return
            context.user_data["admin_state"] = "AWAIT_APPROVE_ID"
            await msg.reply_text("שלח Telegram ID לאישור (מספר בלבד).")
            return

        if data == "ADMIN:REJECT":
            if not self._is_admin(tg.id):
                return
            context.user_data["admin_state"] = "AWAIT_REJECT_ID"
            await msg.reply_text("שלח Telegram ID לדחייה (מספר בלבד).")
            return

    # --------- Text ---------

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
                        db_approve_investor(db, target)
                        await update.message.reply_text(f"✅ אושר משקיע: {target}")
                    elif admin_state == "AWAIT_REJECT_ID":
                        db_reject_investor(db, target)
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
                user = db_get_or_create_user(db, update.effective_user.id, update.effective_user.username)
                db_set_bnb_address(db, user, text)
                await update.message.reply_text(f"✅ נשמרה כתובת BNB:\n{text}")
            finally:
                db.close()
            return

        await update.message.reply_text("לא הבנתי. נסה /menu")


# --------- bootstrap ---------

_bot = InvestorWalletBot()


async def initialize_bot():
    await _bot.initialize()


async def process_webhook(update_dict: dict):
    if not _bot.application:
        return
    update = Update.de_json(update_dict, _bot.application.bot)
    await _bot.application.process_update(update)
