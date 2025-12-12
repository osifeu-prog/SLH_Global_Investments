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
from app import crud, models

logger = logging.getLogger(__name__)

STATE_AWAITING_BNB_ADDRESS = "AWAITING_BNB_ADDRESS"


def _dec(x) -> Decimal:
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal("0")


class InvestorWalletBot:
    def __init__(self) -> None:
        self.application: Application | None = None
        self.bot: Bot | None = None

    # ---------------- DB ----------------

    def _db(self):
        return SessionLocal()

    # ---------------- Auth ----------------

    def _is_admin(self, telegram_id: int) -> bool:
        return bool(settings.ADMIN_USER_ID) and str(telegram_id) == str(settings.ADMIN_USER_ID)

    def _extract_referrer_tid(self, context: ContextTypes.DEFAULT_TYPE) -> int | None:
        """
        Supports /start ref_<tid>
        Stores it once in user_data so /invest can use it.
        """
        try:
            if context.args:
                raw = context.args[0]
                if isinstance(raw, str) and raw.startswith("ref_"):
                    tid = int(raw[4:])
                    return tid
        except Exception:
            pass
        return None

    # ---------------- UI ----------------

    def _menu_kb(self, is_investor: bool, is_admin: bool) -> InlineKeyboardMarkup:
        rows = [
            [
                InlineKeyboardButton("👤 פרופיל", callback_data="M_WHOAMI"),
                InlineKeyboardButton("🎁 הפניות", callback_data="M_REF"),
            ],
            [
                InlineKeyboardButton("🔗 קישור ארנק BNB", callback_data="M_LINK"),
                InlineKeyboardButton("📥 השקעה", callback_data="M_INVEST"),
            ],
        ]

        if is_investor:
            rows.append(
                [
                    InlineKeyboardButton("💰 יתרה", callback_data="M_BAL"),
                    InlineKeyboardButton("🧾 היסטוריה", callback_data="M_HIST"),
                ]
            )

        if is_admin:
            rows.append([InlineKeyboardButton("🛠 אדמין", callback_data="M_ADMIN")])

        return InlineKeyboardMarkup(rows)

    def _admin_kb(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("👮 מועמדים להשקעה", callback_data="A_LIST"),
                    InlineKeyboardButton("✅ אישור עצמי (אני)", callback_data="A_APPROVE_ME"),
                ],
                [
                    InlineKeyboardButton("❌ דחייה עצמי (אני)", callback_data="A_REJECT_ME"),
                    InlineKeyboardButton("⬅️ חזרה לתפריט", callback_data="A_BACK"),
                ],
            ]
        )

    # ---------------- Init ----------------

    async def initialize(self):
        if not settings.BOT_TOKEN:
            logger.warning("BOT_TOKEN not set - bot disabled")
            return

        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        self.bot = self.application.bot

        # user commands
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("menu", self.cmd_menu))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("whoami", self.cmd_whoami))
        self.application.add_handler(CommandHandler("referrals", self.cmd_referrals))
        self.application.add_handler(CommandHandler("link_wallet", self.cmd_link_wallet))
        self.application.add_handler(CommandHandler("invest", self.cmd_invest))
        self.application.add_handler(CommandHandler("balance", self.cmd_balance))
        self.application.add_handler(CommandHandler("history", self.cmd_history))

        # admin commands
        self.application.add_handler(CommandHandler("admin", self.cmd_admin))
        self.application.add_handler(CommandHandler("admin_list_candidates", self.cmd_admin_list_candidates))
        self.application.add_handler(CommandHandler("admin_approve_investor", self.cmd_admin_approve_investor))
        self.application.add_handler(CommandHandler("admin_reject_investor", self.cmd_admin_reject_investor))

        # callbacks (menu + admin)
        self.application.add_handler(CallbackQueryHandler(self.cb_menu, pattern=r"^(M_|A_)"))

        # text handler (BNB address state)
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text)
        )

        # error handler (prevents "silent" failures)
        self.application.add_error_handler(self.on_error)

        await self.application.initialize()

        # webhook
        if settings.WEBHOOK_URL:
            url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook/telegram"
            await self.bot.set_webhook(url)
            logger.info("Webhook set: %s", url)

        logger.info("InvestorWalletBot initialized")

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Unhandled bot error", exc_info=context.error)
        try:
            if isinstance(update, Update) and update.effective_message:
                await update.effective_message.reply_text("⚠️ תקלה זמנית. נסה שוב /menu")
        except Exception:
            pass

    # ---------------- Helpers ----------------

    async def _ensure_user(self, update: Update) -> models.User:
        db = self._db()
        try:
            tg = update.effective_user
            return crud.get_or_create_user(db, tg.id, tg.username)
        finally:
            db.close()

    # ---------------- Commands ----------------

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            user = crud.get_or_create_user(db, tg.id, tg.username)

            # store referrer for later /invest (no DB dependency here)
            ref_tid = self._extract_referrer_tid(context)
            if ref_tid and ref_tid != tg.id:
                context.user_data["referrer_tid"] = ref_tid

            # ensure base wallet exists (if model supports it)
            try:
                crud.get_or_create_wallet(
                    db,
                    telegram_id=tg.id,
                    kind="base",
                    deposits_enabled=True,
                    withdrawals_enabled=False,
                )
            except Exception:
                pass

            is_investor = crud.is_investor_active(db, tg.id)
            is_admin = self._is_admin(tg.id)

            text = (
                "ברוך הבא ל-SLH Global Investments\n\n"
                "✅ נוצר לך חשבון בסיסי.\n"
                "🎁 אפשר לשתף קישור רפררל כבר עכשיו.\n"
                "💼 מסלול השקעה נפתח לאחר Onboarding ואישור אדמין.\n\n"
                "בחר פעולה:"
            )
            await update.message.reply_text(text, reply_markup=self._menu_kb(is_investor, is_admin))
        finally:
            db.close()

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = self._db()
        try:
            await self._ensure_user(update)
            is_investor = crud.is_investor_active(db, update.effective_user.id)
            is_admin = self._is_admin(update.effective_user.id)
            await update.message.reply_text("תפריט ראשי:", reply_markup=self._menu_kb(is_investor, is_admin))
        finally:
            db.close()

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (
            "פקודות:\n"
            "/start /menu\n"
            "/whoami\n"
            "/referrals\n"
            "/link_wallet\n"
            "/invest\n"
            "/balance\n"
            "/history\n\n"
            "אדמין:\n"
            "/admin\n"
            "/admin_list_candidates\n"
            "/admin_approve_investor <telegram_id>\n"
            "/admin_reject_investor <telegram_id>\n"
        )
        await update.message.reply_text(text)

    async def cmd_whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            user = crud.get_or_create_user(db, tg.id, tg.username)

            is_investor = crud.is_investor_active(db, tg.id)
            w_inv = None
            try:
                w_inv = crud.get_wallet(db, tg.id, "investor")
            except Exception:
                w_inv = None

            lines = []
            lines.append("👤 הפרופיל שלך")
            lines.append(f"Telegram ID: {tg.id}")
            lines.append(f"Username: @{tg.username}" if tg.username else "Username: N/A")
            if hasattr(user, "role"):
                lines.append(f"תפקיד: {user.role}")
            if hasattr(user, "bnb_address"):
                lines.append(f"BNB: {user.bnb_address or 'לא קושר'}")
            if hasattr(user, "balance_slh"):
                lines.append(f"SLH: {Decimal(user.balance_slh or 0):.4f}")
            if hasattr(user, "slha_balance"):
                lines.append(f"SLHA: {Decimal(user.slha_balance or 0):.8f}")

            lines.append("")
            lines.append(f"סטטוס משקיע: {'פעיל' if is_investor else 'לא פעיל'}")
            if w_inv and hasattr(w_inv, "deposits_enabled"):
                lines.append(f"ארנק משקיע: {'קיים' if True else 'לא'}")
                lines.append(f"הפקדות: {'✅' if w_inv.deposits_enabled else '❌'}")
                if hasattr(w_inv, "withdrawals_enabled"):
                    lines.append(f"משיכות: {'✅' if w_inv.withdrawals_enabled else '❌'}")
                if hasattr(w_inv, "balance_slh"):
                    lines.append(f"יתרת משקיע (SLH): {Decimal(w_inv.balance_slh or 0):.4f}")

            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    async def cmd_referrals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            crud.get_or_create_user(db, tg.id, tg.username)

            bot_username = None
            try:
                me = await context.bot.get_me()
                bot_username = me.username
            except Exception:
                bot_username = None

            link = f"https://t.me/{bot_username}?start=ref_{tg.id}" if bot_username else "לא הצלחתי לקרוא את שם הבוט כרגע."
            count = crud.count_referrals(db, tg.id)

            user = db.query(models.User).filter(models.User.telegram_id == tg.id).first()
            slha = Decimal(getattr(user, "slha_balance", 0) or 0) if user else Decimal("0")

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
                if user:
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

            if crud.is_investor_active(db, tg.id):
                await update.message.reply_text("✅ אתה כבר משקיע פעיל. השתמש /balance או /history.")
                return

            referrer_tid = context.user_data.get("referrer_tid")
            if referrer_tid is not None:
                try:
                    referrer_tid = int(referrer_tid)
                except Exception:
                    referrer_tid = None

            # ✅ תואם לבוטים קודמים: referrer_tid + risk_ack
            crud.start_invest_onboarding(
                db=db,
                telegram_id=tg.id,
                referrer_tid=referrer_tid,
                note="Requested via bot",
                risk_ack=True,
            )

            await update.message.reply_text(
                "📥 בקשת השקעה נשלחה.\n"
                "⏳ מצב: ממתין לאישור אדמין.\n\n"
                "כשתאושר – ייפתחו יכולות נוספות."
            )
        finally:
            db.close()

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            crud.get_or_create_user(db, tg.id, tg.username)

            if not crud.is_investor_active(db, tg.id):
                await update.message.reply_text("אין לך מסלול השקעה פעיל עדיין. לחץ 📥 השקעה או /invest.")
                return

            w = crud.get_wallet(db, tg.id, "investor")
            bal = Decimal(getattr(w, "balance_slh", 0) or 0) if w else Decimal("0")
            await update.message.reply_text(f"💰 יתרת משקיע פנימית:\n{bal:.4f} SLH")
        finally:
            db.close()

    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        History is optional: only works if you have models.Transaction.
        If not present, we respond gracefully.
        """
        tg = update.effective_user
        db = self._db()
        try:
            crud.get_or_create_user(db, tg.id, tg.username)

            if not hasattr(models, "Transaction"):
                await update.message.reply_text("🧾 היסטוריה עדיין לא זמינה במבנה הנתונים הנוכחי.")
                return

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

            lines = ["🧾 היסטוריה (20 אחרונים):", ""]
            for tx in txs:
                ts = tx.created_at.strftime("%Y-%m-%d %H:%M") if tx.created_at else "N/A"
                amt = Decimal(getattr(tx, "amount_slh", 0) or 0)
                ttype = getattr(tx, "tx_type", "N/A")
                tid = getattr(tx, "id", "N/A")
                lines.append(f"[{ts}] {ttype} | amount={amt:.4f} | id={tid}")

            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    # ---------------- Admin ----------------

    async def cmd_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ אדמין בלבד.")
            return
        await update.message.reply_text("🛠 תפריט אדמין:", reply_markup=self._admin_kb())

    async def cmd_admin_list_candidates(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ אדמין בלבד.")
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

            lines = ["👮 מועמדים (עד 50):", ""]
            for p in cands:
                rid = getattr(p, "telegram_id", "N/A")
                risk = getattr(p, "risk_ack", None)
                created = getattr(p, "created_at", None)
                lines.append(f"- {rid} | risk_ack={risk} | created={created}")
            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    async def cmd_admin_approve_investor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ אדמין בלבד.")
            return

        parts = (update.message.text or "").split()
        if len(parts) != 2:
            await update.message.reply_text("שימוש: /admin_approve_investor <telegram_id>")
            return

        try:
            tid = int(parts[1])
        except Exception:
            await update.message.reply_text("telegram_id לא תקין.")
            return

        db = self._db()
        try:
            crud.get_or_create_user(db, tid, None)
            prof = crud.approve_investor(db, admin_tid=update.effective_user.id, telegram_id=tid)
            await update.message.reply_text(f"✅ אושר משקיע: {tid} (status={getattr(prof, 'status', 'N/A')})")
        finally:
            db.close()

    async def cmd_admin_reject_investor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ אדמין בלבד.")
            return

        parts = (update.message.text or "").split()
        if len(parts) != 2:
            await update.message.reply_text("שימוש: /admin_reject_investor <telegram_id>")
            return

        try:
            tid = int(parts[1])
        except Exception:
            await update.message.reply_text("telegram_id לא תקין.")
            return

        db = self._db()
        try:
            prof = crud.reject_investor(db, admin_tid=update.effective_user.id, telegram_id=tid)
            await update.message.reply_text(f"❌ נדחה משקיע: {tid} (status={getattr(prof, 'status', 'N/A')})")
        finally:
            db.close()

    # ---------------- Callbacks ----------------

    async def cb_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        data = q.data or ""

        # create a fake Update with message as callback message (your older style)
        fake_update = Update(update.update_id, message=q.message)

        # Main menu callbacks
        if data == "M_WHOAMI":
            await self.cmd_whoami(fake_update, context)
            return
        if data == "M_REF":
            await self.cmd_referrals(fake_update, context)
            return
        if data == "M_LINK":
            await self.cmd_link_wallet(fake_update, context)
            return
        if data == "M_INVEST":
            await self.cmd_invest(fake_update, context)
            return
        if data == "M_BAL":
            await self.cmd_balance(fake_update, context)
            return
        if data == "M_HIST":
            await self.cmd_history(fake_update, context)
            return
        if data == "M_ADMIN":
            await self.cmd_admin(fake_update, context)
            return

        # Admin callbacks
        if data == "A_BACK":
            await self.cmd_menu(fake_update, context)
            return

        if not self._is_admin(update.effective_user.id):
            await q.message.reply_text("⛔ אדמין בלבד.")
            return

        if data == "A_LIST":
            await self.cmd_admin_list_candidates(fake_update, context)
            return

        if data == "A_APPROVE_ME":
            # approve the admin as investor (useful for testing)
            db = self._db()
            try:
                prof = crud.approve_investor(db, admin_tid=update.effective_user.id, telegram_id=update.effective_user.id)
                await q.message.reply_text(f"✅ אושרת כמשקיע. status={getattr(prof, 'status', 'N/A')}")
            finally:
                db.close()
            return

        if data == "A_REJECT_ME":
            db = self._db()
            try:
                prof = crud.reject_investor(db, admin_tid=update.effective_user.id, telegram_id=update.effective_user.id)
                await q.message.reply_text(f"❌ נדחית כמשקיע. status={getattr(prof, 'status', 'N/A')}")
            finally:
                db.close()
            return

    # ---------------- Text ----------------

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        state = context.user_data.get("state")
        text = (update.message.text or "").strip()
        tg = update.effective_user

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

        await update.message.reply_text("לא הבנתי. לחץ /menu")


_bot_instance = InvestorWalletBot()


async def initialize_bot():
    await _bot_instance.initialize()


async def process_webhook(update_dict: dict):
    if not _bot_instance.application:
        logger.error("Application is not initialized")
        return
    update = Update.de_json(update_dict, _bot_instance.application.bot)
    await _bot_instance.application.process_update(update)
