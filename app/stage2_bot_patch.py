# Patch for app/bot/investor_wallet_bot.py
# Add these handlers in initialize():
#   self.application.add_handler(CommandHandler("transfer", self.cmd_transfer))
#   self.application.add_handler(CommandHandler("redeem", self.cmd_redeem))
#   self.application.add_handler(CommandHandler("myredemptions", self.cmd_myredemptions))
# Admin:
#   self.application.add_handler(CommandHandler("admin_redemptions", self.cmd_admin_redemptions))
#   self.application.add_handler(CommandHandler("admin_approve_redeem", self.cmd_admin_approve_redeem))
#   self.application.add_handler(CommandHandler("admin_reject_redeem", self.cmd_admin_reject_redeem))
#
# Also ensure /admin_credit exists in your bot (from Stage 1 fix).

from decimal import Decimal
from datetime import date

async def cmd_transfer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("שימוש: /transfer <telegram_id> <amount>")
        return
    try:
        to_tid = int(context.args[0])
        amount = Decimal(str(context.args[1]))
    except Exception:
        await update.message.reply_text("ערכים לא תקינים. דוגמה: /transfer 123456 10")
        return

    db = self._db()
    try:
        try:
            crud.transfer_slha(db, from_tid=tg.id, to_tid=to_tid, amount=amount)
        except Exception as e:
            await update.message.reply_text(f"לא ניתן לבצע העברה: {e}")
            return
        await update.message.reply_text(f"✅ הועברו {amount} SLHA למשתמש {to_tid}")
    finally:
        db.close()


async def cmd_redeem(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    if not context.args:
        await update.message.reply_text("שימוש: /redeem <amount>")
        return
    try:
        amount = Decimal(str(context.args[0]))
    except Exception:
        await update.message.reply_text("סכום לא תקין.")
        return

    db = self._db()
    try:
        prof = crud.get_investor_profile(db, tg.id)
        cohort = getattr(prof, "cohort", None) or "standard"
        policy = "regular"  # Stage 2: we can later compute early/regular by positions
        try:
            req = crud.create_redemption_request(db, telegram_id=tg.id, amount_slha=amount, cohort=cohort, policy=policy)
        except Exception as e:
            await update.message.reply_text(f"לא ניתן ליצור בקשת פדיון: {e}")
            return
        await update.message.reply_text(f"📥 בקשת פדיון נפתחה (ID {req.id}) – ממתין לאישור אדמין.")
    finally:
        db.close()


async def cmd_myredemptions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    db = self._db()
    try:
        rows = db.query(models.RedemptionRequest).filter(models.RedemptionRequest.telegram_id == tg.id).order_by(models.RedemptionRequest.id.desc()).limit(10).all()
        if not rows:
            await update.message.reply_text("אין בקשות פדיון עדיין.")
            return
        lines = ["🧾 בקשות פדיון (10 אחרונות):\n"]
        for r in rows:
            lines.append(f"- #{r.id} | {r.amount_slha} SLHA | {r.status} | {r.created_at}")
        await update.message.reply_text("\n".join(lines))
    finally:
        db.close()


async def cmd_admin_redemptions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not self._is_admin(update.effective_user.id):
        await update.message.reply_text("אין הרשאה.")
        return
    db = self._db()
    try:
        rows = crud.list_redemption_requests(db, status="pending", limit=20)
        if not rows:
            await update.message.reply_text("אין בקשות pending.")
            return
        lines = ["📥 בקשות פדיון ממתינות:\n"]
        for r in rows:
            lines.append(f"- id={r.id} tid={r.telegram_id} amount={r.amount_slha} cohort={r.cohort} policy={r.policy}")
        await update.message.reply_text("\n".join(lines))
    finally:
        db.close()


async def cmd_admin_approve_redeem(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not self._is_admin(update.effective_user.id):
        await update.message.reply_text("אין הרשאה.")
        return
    if not context.args:
        await update.message.reply_text("שימוש: /admin_approve_redeem <id>")
        return
    rid = int(context.args[0])
    db = self._db()
    try:
        row = crud.set_redemption_status(db, req_id=rid, status="approved", note=f"approved_by={update.effective_user.id}")
        if not row:
            await update.message.reply_text("לא נמצא ID כזה.")
            return
        # On-chain hook prepared but NOT executed
        await update.message.reply_text(f"✅ אושר פדיון #{rid}. (On-chain payout hook prepared, not executed)")
    finally:
        db.close()


async def cmd_admin_reject_redeem(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not self._is_admin(update.effective_user.id):
        await update.message.reply_text("אין הרשאה.")
        return
    if not context.args:
        await update.message.reply_text("שימוש: /admin_reject_redeem <id>")
        return
    rid = int(context.args[0])
    db = self._db()
    try:
        row = db.query(models.RedemptionRequest).filter(models.RedemptionRequest.id == rid).first()
        if not row:
            await update.message.reply_text("לא נמצא ID כזה.")
            return
        # Refund locked SLHA back to investor
        amt = Decimal(str(row.amount_slha))
        ledger.create_entry(db, telegram_id=row.telegram_id, wallet_type="investor", direction="in", amount=amt, currency="SLHA", reason="redeem_unlock", meta={"rid": rid, "by": update.effective_user.id})
        row.status = "rejected"
        db.add(row)
        db.commit()
        await update.message.reply_text(f"❌ נדחה פדיון #{rid} והנקודות שוחררו חזרה.")
    finally:
        db.close()
