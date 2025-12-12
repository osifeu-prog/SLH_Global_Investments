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

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.core.config import settings
from app.database import SessionLocal
from app import models
from app import crud

logger = logging.getLogger(__name__)

STATE_AWAITING_BNB_ADDRESS = "AWAITING_BNB_ADDRESS"
STATE_ADMIN_AWAIT_APPROVE_ID = "ADMIN_AWAIT_APPROVE_ID"
STATE_ADMIN_AWAIT_REJECT_ID = "ADMIN_AWAIT_REJECT_ID"


def _dec(x) -> Decimal:
    return Decimal(str(x))


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

    # ========= DB schema safety patch (code-only, no Railway SQL) =========

    def ensure_db_schema(self) -> None:
        """
        מבטיח שעמודת investor_profiles.risk_ack קיימת + NOT NULL + DEFAULT false.
        עובד גם אם בטבלאות יש הבדלים בין סביבה לסביבה.
        """
        db = self._db()
        try:
            # האם העמודה קיימת?
            exists = db.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name='investor_profiles'
                      AND column_name='risk_ack'
                    LIMIT 1
                    """
                )
            ).scalar()

            if not exists:
                db.execute(text("ALTER TABLE investor_profiles ADD COLUMN risk_ack boolean NOT NULL DEFAULT false;"))
                db.commit()
                logger.info("DB patch: added investor_profiles.risk_ack")

            # ודא default + אין NULLs + NOT NULL
            db.execute(text("ALTER TABLE investor_profiles ALTER COLUMN risk_ack SET DEFAULT false;"))
            db.execute(text("UPDATE investor_profiles SET risk_ack=false WHERE risk_ack IS NULL;"))
            db.execute(text("ALTER TABLE investor_profiles ALTER COLUMN risk_ack SET NOT NULL;"))
            db.commit()
            logger.info("DB patch: ensured risk_ack default + not null")
        except ProgrammingError as e:
            db.rollback()
            logger.warning("DB patch skipped/failed (ProgrammingError): %s", e)
        except Exception as e:
            db.rollback()
            logger.exception("DB patch failed: %s", e)
        finally:
            db.close()

    # ========= UI =========

    def _menu_kb(self, is_investor: bool, is_admin: bool) -> InlineKeyboardMarkup:
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

        if is_admin:
            rows.append([InlineKeyboardButton("🛠 פאנל אדמין", callback_data=f"{CB_MENU}ADMIN")])

        rows.append([InlineKeyboardButton("ℹ️ עזרה", callback_data=f"{CB_MENU}HELP")])
        return InlineKeyboardMarkup(rows)

    def _admin_kb(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("👥 הצג מועמדים", callback_data=f"{CB_ADMIN}CANDS")],
                [
                    InlineKeyboardButton("✅ אישור משקיע (הכנס ID)", callback_data=f"{CB_ADMIN}ASK_APPROVE"),
                    InlineKeyboardButton("❌ דחיית משקיע (הכנס ID)", callback_data=f"{CB_ADMIN}ASK_REJECT"),
                ],
                [InlineKeyboardButton("⬅️ חזרה", callback_data=f"{CB_MENU}MENU")],
            ]
        )

    # ========= Init =========

    async def initialize(self):
        if not settings.BOT_TOKEN:
            logger.warning("BOT_TOKEN missing - bot disabled")
            return

        # Patch DB schema before bot starts processing updates
        self.ensure_db_schema()

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

        # Admin
        self.application.add_handler(CommandHandler("admin", self.cmd_admin))
        self.application.add_handler(CommandHandler("admin_approve_investor", self.cmd_admin_approve_investor))
        self.application.add_handler(CommandHandler("admin_reject_investor", self.cmd_admin_reject_investor))

        # Callbacks
        self.application.add_handler(CallbackQueryHandler(self.cb_router, pattern=r"^(M:|A:)"))

        # Text handler
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

        # Error handler
        self.application.add_error_handler(self.on_error)

        await self.application.initialize()

        # Webhook
        if settings.WEBHOOK_URL:
            webhook_url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook/telegram"
            await self.bot.set_webhook(webhook_url)
            logger.info("Webhook set: %s", webhook_url)

        logger.info("InvestorWalletBot initialized")

    async def on_error(self, update, context):
        logger.exception("Unhandled bot error", exc_info=context.error)
        try:
            if update and getattr(update, "effective_message", None):
                await update.effective_message.reply_text("⚠️ תקלה זמנית. נסה שוב /menu")
        except Exception:
            pass

    # ========= Helpers =========

    def _ensure_base_wallet(self, db, telegram_id: int):
        crud.get_or_create_wallet(db, telegram_id, "base", deposits_enabled=True, withdrawals_enabled=False)

    def _investor_wallet_balance(self, db, telegram_id: int) -> Decimal:
        w = (
            db.query(models.Wallet)
            .filter(models.Wallet.telegram_id == telegram_id, models.Wallet.kind == "investor")
            .first()
        )
        if not w:
            return Decimal("0")
        bal = getattr(w, "balance_slh", 0) or 0
        return Decimal(bal)

    # ========= Commands =========

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            user = crud.get_or_create_user(db, tg.id, tg.username)
            self._ensure_base_wallet(db, tg.id)

            # Referral deep-link: /start ref_<tid>
            if context.args:
                raw = context.args[0]
                if isinstance(raw, str) and raw.startswith("ref_"):
                    try:
                        ref_tid = int(raw[4:])
                    except Exception:
                        ref_tid = None
                    if ref_tid and ref_tid != tg.id:
                        # שמירה בטבלת referrals (אם כבר יש referred_tid, UNIQUE ימנע כפילות)
                        try:
                            r = models.Referral(referrer_tid=ref_tid, referred_tid=tg.id)
                            db.add(r)
                            db.commit()
                        except Exception:
                            db.rollback()

            is_inv = crud.is_investor_active(db, tg.id)
            is_admin = self._is_admin(tg.id)

            text = (
                "ברוך הבא ל-SLH Global Investments\n\n"
                "✅ נוצר לך חשבון בסיסי.\n"
                "🎁 אפשר לשתף קישור רפררל כבר עכשיו.\n"
                "💼 מסלול השקעה נפתח לאחר בקשה ואישור אדמין.\n\n"
                "בחר פעולה:"
            )
            await update.message.reply_text(text, reply_markup=self._menu_kb(is_inv, is_admin))
        finally:
            db.close()

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            crud.get_or_create_user(db, tg.id, tg.username)
            self._ensure_base_wallet(db, tg.id)
            is_inv = crud.is_investor_active(db, tg.id)
            await update.message.reply_text("תפריט ראשי:", reply_markup=self._menu_kb(is_inv, self._is_admin(tg.id)))
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
            "/history\n\n"
            "אדמין:\n"
            "/admin\n"
            "/admin_approve_investor <telegram_id>\n"
            "/admin_reject_investor <telegram_id>\n"
        )

    async def cmd_whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            user = crud.get_or_create_user(db, tg.id, tg.username)
            self._ensure_base_wallet(db, tg.id)

            prof = db.query(models.InvestorProfile).filter(models.InvestorProfile.telegram_id == tg.id).first()
            is_inv = crud.is_investor_active(db, tg.id)

            lines = []
            lines.append("👤 הפרופיל שלך")
            lines.append(f"Telegram ID: {tg.id}")
            lines.append(f"Username: @{tg.username}" if tg.username else "Username: N/A")
            lines.append(f"BNB: {user.bnb_address or 'לא קושר'}")
            lines.append(f"SLH פנימי: {Decimal(user.balance_slh or 0):.6f}")
            lines.append(f"SLHA: {Decimal(user.slha_balance or 0):.8f}")
            lines.append(f"סטטוס משקיע: {'פעיל' if is_inv else 'לא פעיל'}")

            if prof:
                lines.append("")
                lines.append("💼 Investor Profile")
                lines.append(f"Status: {prof.status}")
                if hasattr(prof, "risk_ack"):
                    lines.append(f"Risk Ack: {'כן' if prof.risk_ack else 'לא'}")
                if prof.note:
                    lines.append(f"Note: {prof.note}")

            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    async def cmd_referrals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            crud.get_or_create_user(db, tg.id, tg.username)
            count = crud.count_referrals(db, tg.id)

            bot_username = None
            try:
                me = await context.bot.get_me()
                bot_username = me.username
            except Exception:
                bot_username = None

            link = f"https://t.me/{bot_username}?start=ref_{tg.id}" if bot_username else "לא זמין כרגע"
            await update.message.reply_text(
                "🎁 תוכנית הפניות\n\n"
                f"קישור אישי:\n{link}\n\n"
                f"מספר הפניות: {count}\n"
            )
        finally:
            db.close()

    async def cmd_link_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            crud.get_or_create_user(db, tg.id, tg.username)
            self._ensure_base_wallet(db, tg.id)

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
        tg = update.effective_user
        db = self._db()
        try:
            crud.get_or_create_user(db, tg.id, tg.username)
            self._ensure_base_wallet(db, tg.id)

            if crud.is_investor_active(db, tg.id):
                await update.message.reply_text("✅ אתה כבר משקיע פעיל. השתמש /balance או /history.")
                return

            # חשוב: risk_ack תמיד נשלח כדי לא ליפול על NOT NULL
            crud.start_invest_onboarding(
                db,
                telegram_id=tg.id,
                note="Requested via bot",
                risk_ack=True,
            )

            await update.message.reply_text(
                "💼 בקשת השקעה נפתחה בהצלחה.\n"
                "סטטוס: מועמד/ממתין לאישור אדמין.\n\n"
                "אדמין יאשר ואז תקבל אפשרויות נוספות."
            )
        finally:
            db.close()

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg = update.effective_user
        db = self._db()
        try:
            crud.get_or_create_user(db, tg.id, tg.username)

            if not crud.is_investor_active(db, tg.id):
                await update.message.reply_text("אין לך מסלול משקיע פעיל עדיין. לחץ 💼 השקעה או כתוב /invest.")
                return

            bal = self._investor_wallet_balance(db, tg.id)
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
                amt = Decimal(tx.amount_slh or 0)
                lines.append(f"[{ts}] {tx.tx_type} | amount={amt:.6f} | id={tx.id}")
            await update.message.reply_text("\n".join(lines))
        finally:
            db.close()

    # ========= Admin =========

    async def cmd_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ גישה לאדמין בלבד.")
            return
        await update.message.reply_text("🛠 פאנל אדמין:", reply_markup=self._admin_kb())

    async def cmd_admin_approve_investor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Admin only.")
            return

        parts = (update.message.text or "").split()
        if len(parts) != 2:
            await update.message.reply_text("Usage: /admin_approve_investor <telegram_id>")
            return

        try:
            tid = int(parts[1])
        except ValueError:
            await update.message.reply_text("telegram_id לא תקין")
            return

        db = self._db()
        try:
            crud.approve_investor(db, tid)
            await update.message.reply_text(f"✅ אושר משקיע: {tid}")
        finally:
            db.close()

    async def cmd_admin_reject_investor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Admin only.")
            return

        parts = (update.message.text or "").split()
        if len(parts) != 2:
            await update.message.reply_text("Usage: /admin_reject_investor <telegram_id>")
            return

        try:
            tid = int(parts[1])
        except ValueError:
            await update.message.reply_text("telegram_id לא תקין")
            return

        db = self._db()
        try:
            crud.reject_investor(db, tid)
            await update.message.reply_text(f"❌ נדחה משקיע: {tid}")
        finally:
            db.close()

    async def _admin_list_candidates(self, update: Update):
        db = self._db()
        try:
            cands = (
                db.query(models.InvestorProfile)
                .filter(models.InvestorProfile.status.in_(["pending", "candidate"]))
                .order_by(models.InvestorProfile.created_at.asc())
                .limit(50)
                .all()
            )
            if not cands:
                await update.effective_message.reply_text("אין מועמדים כרגע.")
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
                await update.effective_message.reply_text(
                    f"👤 מועמד\nTelegram ID: {p.telegram_id}\nStatus: {p.status}\nNote: {p.note or '-'}",
                    reply_markup=kb,
                )
        finally:
            db.close()

    async def _admin_approve(self, update: Update, tid: int):
        db = self._db()
        try:
            crud.approve_investor(db, tid)
            await update.effective_message.reply_text(f"✅ אושר משקיע: {tid}")
        finally:
            db.close()

    async def _admin_reject(self, update: Update, tid: int):
        db = self._db()
        try:
            crud.reject_investor(db, tid)
            await update.effective_message.reply_text(f"❌ נדחה משקיע: {tid}")
        finally:
            db.close()

    # ========= Callbacks =========

    async def cb_router(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        data = q.data or ""

        fake_update = Update(update.update_id, message=q.message)

        if data.startswith(CB_MENU):
            action = data[len(CB_MENU):]

            if action == "MENU":
                await self.cmd_menu(fake_update, context)
            elif action == "WHOAMI":
                await self.cmd_whoami(fake_update, context)
            elif action == "REF":
                await self.cmd_referrals(fake_update, context)
            elif action == "LINK":
                await self.cmd_link_wallet(fake_update, context)
            elif action == "INVEST":
                await self.cmd_invest(fake_update, context)
            elif action == "BAL":
                await self.cmd_balance(fake_update, context)
            elif action == "HIST":
                await self.cmd_history(fake_update, context)
            elif action == "ADMIN":
                await self.cmd_admin(fake_update, context)
            elif action == "HELP":
                await self.cmd_help(fake_update, context)
            else:
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
                context.user_data["admin_state"] = STATE_ADMIN_AWAIT_APPROVE_ID
                await q.message.reply_text("שלח Telegram ID לאישור (מספר בלבד).")
                return

            if action == "ASK_REJECT":
                context.user_data["admin_state"] = STATE_ADMIN_AWAIT_REJECT_ID
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

    # ========= Text handler =========

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text_msg = (update.message.text or "").strip()
        tg = update.effective_user

        # link wallet
        if context.user_data.get("state") == STATE_AWAITING_BNB_ADDRESS:
            if not text_msg.startswith("0x") or len(text_msg) < 20:
                await update.message.reply_text("כתובת לא תקינה. נסה שוב /link_wallet.")
                return

            db = self._db()
            try:
                user = crud.get_or_create_user(db, tg.id, tg.username)
                crud.set_bnb_address(db, user, text_msg)
                context.user_data["state"] = None
                await update.message.reply_text(f"✅ נשמרה כתובת BNB:\n{text_msg}")
            finally:
                db.close()
            return

        # admin ID input
        admin_state = context.user_data.get("admin_state")
        if admin_state in (STATE_ADMIN_AWAIT_APPROVE_ID, STATE_ADMIN_AWAIT_REJECT_ID):
            if not self._is_admin(tg.id):
                context.user_data["admin_state"] = None
                await update.message.reply_text("⛔ גישה לאדמין בלבד.")
                return

            if not text_msg.isdigit():
                await update.message.reply_text("שלח מספר Telegram ID בלבד.")
                return

            tid = int(text_msg)
            context.user_data["admin_state"] = None

            if admin_state == STATE_ADMIN_AWAIT_APPROVE_ID:
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
        logger.error("Application is not initialized")
        return
    update = Update.de_json(update_dict, _bot_instance.application.bot)
    await _bot_instance.application.process_update(update)
