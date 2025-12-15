#!/usr/bin/env python3
import logging
import sqlite3
import asyncio
from datetime import datetime, timedelta

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ================= CONFIG =================
BOT_TOKEN = "8306233846:AAGdHTLKmrspRYTg2U850EV5GpF1jUy1MtA"
ADMIN_IDS = [6567632240]

REQUIRED_GROUP = "@v1defyv"
REQUIRED_CHANNEL = "@defy_portal"

DB_PATH = "files_all.db"

UTR_TIMEOUT_MINUTES = 10
CHECK_INTERVAL_SECONDS = 60
# =========================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

# ================= DATABASE =================
cur.execute("""
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT,
    file_name TEXT,
    category TEXT,
    is_paid INTEGER,
    price TEXT,
    payment_qr_file_id TEXT,
    upload_time TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    file_row_id INTEGER,
    status TEXT,
    utr TEXT,
    requested_at TEXT
)
""")
conn.commit()

# ================= UI =================
def admin_purchase_kb(pid):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{pid}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{pid}")
        ]
    ])

# ================= START =================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to File Store Bot.")

# ================= PAID FLOW =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    # ===== I PAID =====
    if data.startswith("paid_notify:"):
        pid = int(data.split(":")[1])

        cur.execute(
            "UPDATE purchases SET status=?, requested_at=? WHERE id=?",
            ("awaiting_utr", datetime.utcnow().isoformat(), pid)
        )
        conn.commit()

        context.user_data["awaiting_utr"] = pid

        await q.message.reply_text(
            "✅ *Payment initiated*\n\n"
            "🧾 Please send your *UTR / Transaction ID* within "
            f"*{UTR_TIMEOUT_MINUTES} minutes*.\n\n"
            "⚠️ If not submitted in time, the order will be auto-cancelled.",
            parse_mode="Markdown"
        )
        return

    # ===== ADMIN APPROVE =====
    if data.startswith("approve:"):
        if uid not in ADMIN_IDS:
            return
        pid = int(data.split(":")[1])

        cur.execute("""
            SELECT p.user_id, f.file_id, f.file_name
            FROM purchases p
            JOIN files f ON p.file_row_id=f.id
            WHERE p.id=?
        """, (pid,))
        r = cur.fetchone()

        if not r:
            return

        buyer, file_id, fname = r

        cur.execute("UPDATE purchases SET status='approved' WHERE id=?", (pid,))
        conn.commit()

        await context.bot.send_document(
            chat_id=buyer,
            document=file_id,
            caption=f"✅ Payment approved\n📄 {fname}"
        )

        await q.message.reply_text("✅ Approved & file sent.")
        return

    # ===== ADMIN REJECT =====
    if data.startswith("reject:"):
        if uid not in ADMIN_IDS:
            return
        pid = int(data.split(":")[1])

        cur.execute("SELECT user_id FROM purchases WHERE id=?", (pid,))
        buyer = cur.fetchone()[0]

        cur.execute("UPDATE purchases SET status='rejected' WHERE id=?", (pid,))
        conn.commit()

        await context.bot.send_message(
            buyer,
            "❌ Your payment was rejected by admin."
        )
        await q.message.reply_text("Rejected.")
        return

# ================= TEXT (UTR) =================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    text = update.message.text.strip()

    if context.user_data.get("awaiting_utr"):
        pid = context.user_data.pop("awaiting_utr")

        cur.execute(
            "UPDATE purchases SET utr=?, status='pending' WHERE id=?",
            (text, pid)
        )
        conn.commit()

        cur.execute("""
            SELECT p.user_id, f.file_name, f.price
            FROM purchases p
            JOIN files f ON p.file_row_id=f.id
            WHERE p.id=?
        """, (pid,))
        u, fname, price = cur.fetchone()

        for aid in ADMIN_IDS:
            await context.bot.send_message(
                aid,
                f"💳 *Payment Verification*\n\n"
                f"📄 File: {fname}\n"
                f"👤 User: {u}\n"
                f"💰 Price: {price}\n"
                f"🧾 UTR: `{text}`\n"
                f"🆔 Order ID: {pid}",
                parse_mode="Markdown",
                reply_markup=admin_purchase_kb(pid)
            )

        await update.message.reply_text(
            "✅ UTR received.\n⏳ Awaiting admin verification."
        )

# ================= AUTO-CANCEL TASK =================
async def auto_cancel_task(app):
    while True:
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

        expiry = datetime.utcnow() - timedelta(minutes=UTR_TIMEOUT_MINUTES)

        cur.execute("""
            SELECT id, user_id FROM purchases
            WHERE status='awaiting_utr' AND requested_at < ?
        """, (expiry.isoformat(),))

        expired = cur.fetchall()

        for pid, uid in expired:
            cur.execute(
                "UPDATE purchases SET status='cancelled' WHERE id=?",
                (pid,)
            )
            conn.commit()

            try:
                await app.bot.send_message(
                    uid,
                    "⌛ *Order Cancelled*\n\n"
                    "UTR was not submitted in time.\n"
                    "Please place a new order if needed.",
                    parse_mode="Markdown"
                )
            except:
                pass

            for aid in ADMIN_IDS:
                await app.bot.send_message(
                    aid,
                    f"⌛ Order #{pid} auto-cancelled (UTR timeout)."
                )

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.job_queue.run_once(
        lambda ctx: asyncio.create_task(auto_cancel_task(app)), 1
    )

    logger.info("Bot started with UTR auto-cancel enabled")
    app.run_polling()

if __name__ == "__main__":
    main()
