import logging
from decimal import Decimal

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from sqlalchemy import or_

from app.core.config import settings
from app.database import SessionLocal
from app import models, crud
from app.monitoring import run_selftest

logger = logging.getLogger(__name__)

STATE_AWAITING_BNB_ADDRESS = "AWAITING_BNB_ADDRESS"


class InvestorWalletBot:
    def __init__(self):
        self.application: Application | None = None
        self.bot: Bot | None = None

    # ---------------- DB ----------------

    def _db(self):
        return SessionLocal()

    # ---------------- Admin ----------------

    def _is_admin(self, telegram_id: int) -> bool:
        return bool(settings.ADMIN_USER_ID) and str(telegram_id) == str(
            settings.ADMIN_USER_ID
        )

    # ---------------- Init ----------------

    async def initialize(self):
        if not settings.BOT_TOKEN:
            logger.warning("BOT_TOKEN missing, bot disabled")
            return

        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        self.bot = self.application.bot

        # commands
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("menu", self.cmd_menu))
        self.application.add_handler(CommandHandler("wallet", self.cmd_wallet))
        self.application.add_handler(CommandHandler("link_wallet", self.cmd_link_wallet))
        self.application.add_handler(CommandHandler("whoami", self.cmd_whoami))
        self.application.add_handler(CommandHandler("referrals", self.cmd_referrals))
        self.application.add_handler(CommandHandler("invest", self.cmd_invest))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("ping", self.cmd_ping))

        # admin
        self.application.add_handler(
            CommandHandler("admin_approve_investor", self.cmd_admin_approve_investor)
        )
        self.application.add_handler(
            CommandHandler("admin_reject_investor", self.cmd_admin_reject_investor)
        )

        # text handler
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text)
        )

        # error handler
        self.application.add_error_handler(self.on_error)

        await self.application.initialize()

        # webhook
        if settings.WEBHOOK_URL:
            url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook/telegram"
            await self.bot.set_webhook(url)
            logger.info(f"Webhook set: {url}")

        logger.info("InvestorWalletBot initialized")

    # ---------------- Errors ----------------

    async def on_error(self, update, context):
        logger.exception("Unhandled bot error", exc_info=context.error)
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "⚠️ תקלה זמנית במערכת. אם זה חוזר, שלח /start מחדש."
                )
        except Exception:
            pass

    # ---------------- UI ----------------

    def _main_menu(self):
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("👤 מי אני", callback_data="WHOAMI"),
                    InlineKeyboardButton("💼 ארנק", callback_data="WALLET"),
                ],
                [
                    InlineKeyboardButton("🎁 רפררלים", callback_data="REFERRALS"),
                    InlineKeyboardButton("📥 השקעה", callback_data="INVEST"),
                ],
            ]
        )

    # ---------------- Commands ----------------

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            user = crud.get_or_create_user(db, tg.id, tg.username)

            # base wallet תמיד קיים
            crud.get_or_create_wallet(
                db,
                telegram_id=tg.id,
                kind="base",
                deposits_enabled=True,
                withdrawals_enabled=False,
            )

            text = (
                "ברוך הבא ל-SLH Global Investments\n\n"
                "✅ נוצר לך חשבון בסיסי.\n"
                "🎁 אפשר לשתף קישור רפררל כבר עכשיו.\n"
                "💼 מסלול השקעה (Investor Wallet) נפתח רק לאחר Onboarding ואישור אדמין.\n\n"
                "השתמש בתפריט:"
            )

            await update.message.reply_text(text, reply_markup=self._main_menu())
        finally:
            db.close()

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "תפריט ראשי:", reply_markup=self._main_menu()
        )

    async def cmd_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = self._db()
        try:
            tg = update.effective_user
            user = crud.get_or_create_user(db, tg.id, tg.username)

            wallets = (
                db.query(models.Wallet)
                .filter(models.Wallet.telegram_id == tg.id)
                .all()
            )

            lines = ["💼 הארנקים שלך:\n"]
            for w in wallets:
                lines.append(
                    f"- {w.kind.upper()} | "
                    f"הפקדות: {'✅' if w.deposits_enabled else '❌'} | "
                    f"משיכות: {'✅' if w.withdrawals_enabled else '❌'}"
                )

            lines.append("")
            lines.append(f"BNB: {user.bnb_address or 'לא מחובר'}")

            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    async def cmd_link_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data["state"] = STATE_AWAITING_BNB_ADDRESS
        await update.message.reply_text("שלח עכשיו כתובת BNB (מתחילה ב-0x...)")

    async def cmd_whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = self._db()
        try:
            tg = update.effective_user
            user = crud.get_or_create_user(db, tg.id, tg.username)

            is_investor = crud.is_investor_active(db, tg.id)

            text = (
                "👤 פרופיל משתמש\n\n"
                f"ID: {tg.id}\n"
                f"Username: @{tg.username}\n"
                f"BNB: {user.bnb_address or 'לא מחובר'}\n"
                f"SLH: {user.balance_slh:.4f}\n"
                f"SLHA: {user.slha_balance:.8f}\n\n"
                f"סטטוס משקיע: {'פעיל' if is_investor else 'לא פעיל'}"
            )

            await update.message.reply_text(text)
        finally:
            db.close()

    async def cmd_referrals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = self._db()
        try:
            tg = update.effective_user
            count = crud.count_referrals(db, tg.id)

            link = f"https://t.me/{self.bot.username}?start=ref_{tg.id}"

            text = (
                "🎁 תוכנית רפררלים\n\n"
                f"קישור אישי:\n{link}\n\n"
                f"מצטרפים דרך הקישור: {count}\n\n"
                "כל הצטרפות מזכה בנקודות SLHA."
            )

            await update.message.reply_text(text)
        finally:
            db.close()

    async def cmd_invest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = self._db()
        try:
            tg = update.effective_user

            if crud.is_investor_active(db, tg.id):
                await update.message.reply_text("כבר יש לך מסלול השקעה פעיל.")
                return

            crud.start_invest_onboarding(
                db,
                telegram_id=tg.id,
                note="Requested via bot",
            )

            await update.message.reply_text(
                "📥 בקשת השקעה נשלחה.\n"
                "ארנק משקיע נוצר (הפקדות בלבד).\n"
                "לאחר אישור אדמין – ייפתחו יכולות נוספות."
            )
        finally:
            db.close()

    # ---------------- Admin ----------------

    async def cmd_admin_approve_investor(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if not self._is_admin(update.effective_user.id):
            return

        parts = update.message.text.split()
        if len(parts) < 2:
            await update.message.reply_text("Usage: /admin_approve_investor <telegram_id>")
            return

        target = int(parts[1])
        db = self._db()
        try:
            prof = (
                db.query(models.InvestorProfile)
                .filter(models.InvestorProfile.telegram_id == target)
                .first()
            )
            if not prof:
                await update.message.reply_text("Investor profile not found.")
                return

            prof.status = "active"
            db.commit()

            wallet = crud.get_or_create_wallet(
                db,
                telegram_id=target,
                kind="investor",
            )
            wallet.withdrawals_enabled = False
            db.commit()

            await update.message.reply_text(f"✅ Investor {target} approved.")
        finally:
            db.close()

    async def cmd_admin_reject_investor(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if not self._is_admin(update.effective_user.id):
            return

        parts = update.message.text.split()
        if len(parts) < 2:
            await update.message.reply_text("Usage: /admin_reject_investor <telegram_id>")
            return

        target = int(parts[1])
        db = self._db()
        try:
            prof = (
                db.query(models.InvestorProfile)
                .filter(models.InvestorProfile.telegram_id == target)
                .first()
            )
            if not prof:
                await update.message.reply_text("Investor profile not found.")
                return

            prof.status = "rejected"
            db.commit()

            await update.message.reply_text(f"❌ Investor {target} rejected.")
        finally:
            db.close()

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "/start\n/menu\n/whoami\n/wallet\n/link_wallet\n/referrals\n/invest"
        )

    async def cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("pong")

    # ---------------- Text ----------------

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        state = context.user_data.get("state")
        text = update.message.text.strip()

        if state == STATE_AWAITING_BNB_ADDRESS:
            context.user_data["state"] = None
            if not text.startswith("0x"):
                await update.message.reply_text("כתובת לא תקינה.")
                return

            db = self._db()
            try:
                user = crud.get_or_create_user(
                    db,
                    update.effective_user.id,
                    update.effective_user.username,
                )
                crud.set_bnb_address(db, user, text)
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
