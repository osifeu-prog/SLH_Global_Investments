# app/bot/investor_wallet_bot.py
from __future__ import annotations

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

from app.core.config import settings
from app.database import SessionLocal
from app import models
from app import crud

logger = logging.getLogger(__name__)

STATE_AWAITING_BNB_ADDRESS = "AWAITING_BNB_ADDRESS"


def _dec(x) -> Decimal:
    return Decimal(str(x))


# ====== Callback codes ======
CB_MENU = "M:"
CB_ADMIN = "A:"


class InvestorWalletBot:
    def __init__(self) -> None:
        self.application: Application | None = None
        self.bot: Bot | None = None

    def _db(self):
        return SessionLocal()

    def _is_admin(self, user_id: int) -> bool:
        return bool(settings.ADMIN_USER_ID) and str(user_id) == str(settings.ADMIN_USER_ID)

    # ========== UI ==========

    def _main_menu(self, is_investor: bool) -> InlineKeyboardMarkup:
        rows = [
            [
                InlineKeyboardButton("👤 פרופיל", callback_data=f"{CB_MENU}WHOAMI"),
                InlineKeyboardButton("🎁 הפניות", callback_data=f"{CB_MENU}REF"),
            ],
            [
                InlineKeyboardButton("🔗 קישור כתובת BNB", callback_data=f"{CB_MENU}LINK"),
                InlineKeyboardButton("💼 השקעה", callback_data=f"{CB_MENU}INVEST"),
            ],
        ]
        if is_investor:
            rows.append(
                [
                    InlineKeyboardButton("💰 יתרה", callback_data=f"{CB_MENU}BAL"),
                    InlineKeyboardButton("🧾 היסטוריה", callback_data=f"{CB_MENU}HIST"),
                ]
            )

        if settings.ADMIN_USER_ID:
            rows.append([InlineKeyboardButton("🛠 אדמין", callback_data=f"{CB_MENU}ADMIN")])

        return InlineKeyboardMarkup(rows)

    def _admin_menu(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("👥 מועמדים להשקעה", callback_data=f"{CB_ADMIN}CANDS")],
                [InlineKeyboardButton("✅ אישור משקיע (ID)", callback_data=f"{CB_ADMIN}ASK_APPROVE")],
                [InlineKeyboardButton("❌ דחיית משקיע (ID)", callback_data=f"{CB_ADMIN}ASK_REJECT")],
                [InlineKeyboardButton("⬅️ חזרה לתפריט", callback_data=f"{CB_MENU}MENU")],
            ]
        )

    # ========== Init / Webhook ==========

    async def initialize(self):
        if not settings.BOT_TOKEN:
            logger.warning("BOT_TOKEN not set - bot disabled")
            return

        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        self.bot = self.application.bot

        # Commands
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("menu", self.cmd_menu))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("whoami", self.cmd_whoami))
        self.application.add_handler(CommandHandler("referrals", self.cmd_referrals))
        self.application.add_handler(CommandHandler("link_wallet", self.cmd_link_wallet))
        self.application.add_handler(CommandHandler("invest", self.cmd_invest))
        self.application.add_handler(CommandHandler("balance", self.cmd_balance))
        self.application.add_handler(CommandHandler("history", self.cmd_history))
        self.application.add_handler(CommandHandler("admin", self.cmd_admin))

        # Callbacks
        self.application.add_handler(CallbackQueryHandler(self.cb_router, pattern=r"^(M:|A:)"))

        # Text handler (states)
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

        # Error handler (כדי שלא יהיו 502/נפילות שקטות)
        self.application.add_error_handler(self.on_error)

        await self.application.initialize()

        if settings.WEBHOOK_URL:
            webhook_url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook/telegram"
            await self.bot.set_webhook(webhook_url)
            logger.info("Webhook set: %s", webhook_url)

        logger.info("InvestorWalletBot initialized")

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Unhandled bot error", exc_info=context.error)
        try:
            if isinstance(update, Update) and update.effective_message:
                await update.effective_message.reply_text("⚠️ תקלה זמנית. נסה שוב /menu")
        except Exception:
            pass

    # ========== Helpers ==========

    async def _ensure_user(self, update: Update) -> models.User:
        tg = update.effective_user
        db = self._db()
        try:
            user = crud.get_or_create_user(db, tg.id, tg.username)
            # ודא base wallet תמיד קיים
            crud.get_or_create_wallet(db, tg.id, "base", deposits_enabled=True, withdrawals_enabled=False)
            return user
        finally:
            db.close()

    def _get_investor_wallet_balance(self, db, telegram_id: int) -> Decimal:
        w = (
            db.query(models.Wallet)
            .filter(models.Wallet.telegram_id == telegram_id, models.Wallet.kind == "investor")
            .first()
        )
        if not w or not hasattr(w, "balance_slh"):
            return Decimal("0")
        return Decimal(w.balance_slh or 0)

    # ========== Commands ==========

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = self._db()
        try:
            tg = update.effective_user
            user = crud.get_or_create_user(db, tg.id, tg.username)
            crud.get_or_create_wallet(db, tg.id, "base", deposits_enabled=True, withdrawals_enabled=False)

            # Referral: /start ref_<tid>
            if context.args:
                raw = context.args[0]
                if isinstance(raw, str) and raw.startswith("ref_"):
                    try:
                        ref_tid = int(raw[4:])
                    except ValueError:
                        ref_tid = None
                    if ref_tid and ref_tid != tg.id:
                        # אם יש לך מנגנון "register_referral" – תוסיף אותו ב-crud בעתיד.
                        # כרגע אנחנו רק שומרים Referral בטבלה הקיימת אם תרצה בהמשך.
                        pass

            is_investor = crud.is_investor_active(db, tg.id)
            text = (
                "ברוך הבא ל-SLH Global Investments\n\n"
                "✅ נוצר לך חשבון בסיסי.\n"
                "🎁 אפשר לשתף קישור רפררל כבר עכשיו.\n"
                "💼 מסלול השקעה נפתח רק לאחר בקשה ואישור אדמין.\n\n"
                "בחר פעולה:"
            )
            await update.message.reply_text(text, reply_markup=self._main_menu(is_investor))
        finally:
            db.close()

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = self._db()
        try:
            await self._ensure_user(update)
            is_investor = crud.is_investor_active(db, update.effective_user.id)
            await update.message.reply_text("תפריט ראשי:", reply_markup=self._main_menu(is_investor))
        finally:
            db.close()

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "פקודות:\n"
            "/start /menu\n"
            "/whoami\n"
            "/referrals\n"
            "/link_wallet\n"
            "/invest\n"
            "/balance\n"
            "/history\n"
            "\nאדמין:\n"
            "/admin\n"
            "/admin_approve <telegram_id>\n"
            "/admin_reject <telegram_id>\n"
        )

    async def cmd_whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = self._db()
        try:
            tg = update.effective_user
            user = crud.get_or_create_user(db, tg.id, tg.username)

            prof = db.query(models.InvestorProfile).filter(models.InvestorProfile.telegram_id == tg.id).first()
            wallets = db.query(models.Wallet).filter(models.Wallet.telegram_id == tg.id).all()
            is_investor = crud.is_investor_active(db, tg.id)

            lines = []
            lines.append("👤 הפרופיל שלך")
            lines.append(f"Telegram ID: {tg.id}")
            lines.append(f"Username: @{tg.username}" if tg.username else "Username: N/A")
            lines.append(f"BNB: {user.bnb_address or 'לא קושר'}")
            lines.append(f"SLH (פנימי): {Decimal(user.balance_slh or 0):.6f}")
            lines.append(f"SLHA: {Decimal(user.slha_balance or 0):.8f}")
            lines.append(f"סטטוס משקיע: {'פעיל' if is_investor else 'לא פעיל'}")

            if prof:
                lines.append("")
                lines.append("💼 Investor Profile:")
                lines.append(f"Status: {prof.status}")
                if getattr(prof, "note", None):
                    lines.append(f"Note: {prof.note}")

            if wallets:
                lines.append("")
                lines.append("💳 ארנקים:")
                for w in wallets:
                    lines.append(
                        f"- {w.kind} | הפקדות: {'✅' if w.deposits_enabled else '❌'} | משיכות: {'✅' if w.withdrawals_enabled else '❌'}"
                    )

            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    async def cmd_referrals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = self._db()
        try:
            tg = update.effective_user
            crud.get_or_create_user(db, tg.id, tg.username)

            bot_username = None
            try:
                me = await context.bot.get_me()
                bot_username = me.username
            except Exception:
                bot_username = None

            link = f"https://t.me/{bot_username}?start=ref_{tg.id}" if bot_username else "לא הצלחתי לקרוא שם בוט."
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
            crud.get_or_create_user(db, tg.id, tg.username)

            if context.args:
                addr = context.args[0].strip()
                if not addr.startswith("0x") or len(addr) < 20:
                    await update.message.reply_text("כתובת לא תקינה. דוגמה: /link_wallet 0xABC...")
                    return
                user = db.query(models.User).filter(models.User.telegram_id == tg.id).first()
                crud.set_bnb_address(db, user, addr)
                await update.message.reply_text(f"✅ נשמרה כתובת BNB:\n{addr}")
                context.user_data["state"] = None
                return

            context.user_data["state"] = STATE_AWAITING_BNB_ADDRESS
            await update.message.reply_text("שלח עכשיו כתובת BNB (מתחילה ב-0x...)")
        finally:
            db.close()

    async def cmd_invest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        פתיחת בקשת השקעה.
        קריטי: תמיד להעביר risk_ack כדי לא ליפול על NOT NULL אם קיים.
        """
        db = self._db()
        try:
            tg = update.effective_user
            crud.get_or_create_user(db, tg.id, tg.username)

            # כבר פעיל?
            if crud.is_investor_active(db, tg.id):
                await update.message.reply_text("✅ אתה כבר משקיע פעיל. השתמש /balance או /history.")
                return

            # יצירת Candidate
            # risk_ack=True (כרגע בלי שאלון; בעתיד נעשה שאלון אינליין)
            crud.start_invest_onboarding(db, telegram_id=tg.id, note="Requested via bot", risk_ack=True)

            await update.message.reply_text(
                "💼 הבקשה נפתחה בהצלחה.\n"
                "סטטוס: מועמד (Candidate)\n\n"
                "השלב הבא: אישור אדמין.\n"
                "לאחר אישור – תקבל אפשרויות נוספות."
            )
        finally:
            db.close()

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = self._db()
        try:
            tg = update.effective_user
            crud.get_or_create_user(db, tg.id, tg.username)

            if not crud.is_investor_active(db, tg.id):
                await update.message.reply_text("אין לך מסלול משקיע פעיל עדיין. לחץ 💼 השקעה או כתוב /invest.")
                return

            bal = self._get_investor_wallet_balance(db, tg.id)
            await update.message.reply_text(f"💰 יתרת משקיע פנימית:\n{bal:.4f} SLH")
        finally:
            db.close()

    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = self._db()
        try:
            tg = update.effective_user
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
                lines.append(f"[{ts}] {tx.tx_type} | amount={Decimal(tx.amount_slh or 0):.6f} | id={tx.id}")
            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    # ========== Admin ==========

    async def cmd_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ גישה לאדמין בלבד.")
            return
        await update.message.reply_text("🛠 פאנל אדמין:", reply_markup=self._admin_menu())

    async def _admin_list_candidates(self, chat_update: Update):
        db = self._db()
        try:
            cands = (
                db.query(models.InvestorProfile)
                .filter(models.InvestorProfile.status.in_(["pending", "candidate"]))
                .order_by(models.InvestorProfile.created_at.asc())
                .limit(20)
                .all()
            )
            if not cands:
                await chat_update.effective_message.reply_text("אין מועמדים כרגע.")
                return

            for p in cands:
                kb = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("✅ אשר", callback_data=f"{CB_ADMIN}APPROVE:{p.telegram_id}"),
                            InlineKeyboardButton("❌ דחה", callback_data=f"{CB_ADMIN}REJECT:{p.telegram_id}"),
                        ]
                    ]
                )
                await chat_update.effective_message.reply_text(
                    f"👤 מועמד\nTelegram ID: {p.telegram_id}\nStatus: {p.status}\nNote: {p.note or '-'}",
                    reply_markup=kb,
                )
        finally:
            db.close()

    async def _admin_approve(self, chat_update: Update, target_tid: int):
        db = self._db()
        try:
            crud.approve_investor(db, target_tid)
            await chat_update.effective_message.reply_text(f"✅ אושר משקיע: {target_tid}")
        finally:
            db.close()

    async def _admin_reject(self, chat_update: Update, target_tid: int):
        db = self._db()
        try:
            crud.reject_investor(db, target_tid)
            await chat_update.effective_message.reply_text(f"❌ נדחה משקיע: {target_tid}")
        finally:
            db.close()

    # ========== Callbacks ==========

    async def cb_router(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        data = q.data or ""

        # ניצור fake update כדי להשתמש באותן פונקציות שמשתמשות ב-update.message
        fake_update = Update(update.update_id, message=q.message)

        if data.startswith(CB_MENU):
            action = data[len(CB_MENU):]

            if action == "MENU":
                await self.cmd_menu(fake_update, context)
                return
            if action == "WHOAMI":
                await self.cmd_whoami(fake_update, context)
                return
            if action == "REF":
                await self.cmd_referrals(fake_update, context)
                return
            if action == "LINK":
                await self.cmd_link_wallet(fake_update, context)
                return
            if action == "INVEST":
                await self.cmd_invest(fake_update, context)
                return
            if action == "BAL":
                await self.cmd_balance(fake_update, context)
                return
            if action == "HIST":
                await self.cmd_history(fake_update, context)
                return
            if action == "ADMIN":
                await self.cmd_admin(fake_update, context)
                return

            await q.message.reply_text("לא הבנתי. /menu")
            return

        if data.startswith(CB_ADMIN):
            if not self._is_admin(update.effective_user.id):
                await q.message.reply_text("⛔ גישה לאדמין בלבד.")
                return

            action = data[len(CB_ADMIN):]

            if action == "CANDS":
                await self._admin_list_candidates(fake_update)
                return

            if action == "ASK_APPROVE":
                context.user_data["admin_state"] = "AWAIT_APPROVE_ID"
                await q.message.reply_text("שלח Telegram ID לאישור (מספר בלבד).")
                return

            if action == "ASK_REJECT":
                context.user_data["admin_state"] = "AWAIT_REJECT_ID"
                await q.message.reply_text("שלח Telegram ID לדחייה (מספר בלבד).")
                return

            if action.startswith("APPROVE:"):
                tid = int(action.split(":", 1)[1])
                await self._admin_approve(fake_update, tid)
                return

            if action.startswith("REJECT:"):
                tid = int(action.split(":", 1)[1])
                await self._admin_reject(fake_update, tid)
                return

            await q.message.reply_text("אדמין: פעולה לא מוכרת.")
            return

    # ========== Text / States ==========

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (update.message.text or "").strip()
        tg = update.effective_user

        # Link wallet state
        state = context.user_data.get("state")
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

        # Admin manual approve/reject states
        admin_state = context.user_data.get("admin_state")
        if admin_state in ("AWAIT_APPROVE_ID", "AWAIT_REJECT_ID"):
            if not self._is_admin(tg.id):
                context.user_data["admin_state"] = None
                await update.message.reply_text("⛔ גישה לאדמין בלבד.")
                return
            if not text.isdigit():
                await update.message.reply_text("שלח מספר Telegram ID בלבד.")
                return
            tid = int(text)
            context.user_data["admin_state"] = None
            if admin_state == "AWAIT_APPROVE_ID":
                await self._admin_approve(update, tid)
            else:
                await self._admin_reject(update, tid)
            return

        await update.message.reply_text("לא הבנתי. השתמש /menu")


_bot_instance = InvestorWalletBot()


async def initialize_bot():
    await _bot_instance.initialize()


async def process_webhook(update_dict: dict):
    if not _bot_instance.application:
        logger.error("Bot application is not initialized")
        return
    update = Update.de_json(update_dict, _bot_instance.application.bot)
    await _bot_instance.application.process_update(update)
