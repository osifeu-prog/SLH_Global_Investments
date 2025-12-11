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

    def _get_lang(self, tg_user, context: ContextTypes.DEFAULT_TYPE | None = None) -> str:
        override = context.user_data.get("lang") if context else None
        if override:
            return i18n.normalize_lang(override)
        raw = getattr(tg_user, "language_code", None) or settings.DEFAULT_LANGUAGE
        return i18n.normalize_lang(raw)

    async def initialize(self):
        if not settings.BOT_TOKEN:
            logger.warning("BOT_TOKEN not set - skipping bot init")
            return

        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        self.bot = self.application.bot

        # user
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("menu", self.cmd_menu))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("whoami", self.cmd_whoami))
        self.application.add_handler(CommandHandler("referrals", self.cmd_referrals))
        self.application.add_handler(CommandHandler("link_wallet", self.cmd_link_wallet))

        # investor flow
        self.application.add_handler(CommandHandler("invest", self.cmd_invest))
        self.application.add_handler(CommandHandler("deposit", self.cmd_deposit))
        self.application.add_handler(CommandHandler("balance", self.cmd_balance))
        self.application.add_handler(CommandHandler("history", self.cmd_history))

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
            "/deposit (דיווח הפקדה)\n\n"
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

            # נרשום candidate + risk_ack=true (פשוט ומהיר; אפשר להפוך לשאלון בהמשך)
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
