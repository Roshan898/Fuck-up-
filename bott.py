#!/usr/bin/env python3
# =================================================
# Viral Video Bot with Preview + Prev/Next Buttons
# Single Script | Render Ready
# =================================================

import logging
import sqlite3
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ===================== CONFIG =====================
BOT_TOKEN = "8359828511:AAH-TBlWFfDH_3T_MRM8YPULbb52mH3z12g"
ADMIN_ID = 6567632240           # your Telegram numeric ID
FORCE_JOIN = "@duvkuppp"    # channel or group username
HOW_TO_WATCH_LINK = "https://t.me/yourchannel/123"
# =================================================

logging.basicConfig(level=logging.INFO)

# ===================== DATABASE ===================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    link TEXT,
    preview_file_id TEXT,
    preview_type TEXT,
    created_at TEXT
)
""")
conn.commit()

# ===================== STATE ======================
user_states = {}
user_pages = {}  # user_id -> index

# ================= FORCE JOIN =====================
async def is_joined(bot, user_id):
    try:
        m = await bot.get_chat_member(FORCE_JOIN, user_id)
        return m.status in ("member", "administrator", "creator")
    except:
        return False

# ================= SEND PREVIEW ===================
async def send_card(bot, chat_id, video, index, total):
    title, link, file_id, file_type = video
    caption = f"<b>{title}</b>\n{link}\n\n📄 {index+1}/{total}"

    buttons = []
    if index > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data="prev"))
    if index < total - 1:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data="next"))

    reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None

    if file_id and file_type == "photo":
        await bot.send_photo(chat_id, file_id, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
    elif file_id and file_type == "video":
        await bot.send_video(chat_id, file_id, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=reply_markup)

# ===================== START ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not await is_joined(context.bot, user.id):
        btn = [[InlineKeyboardButton("✅ Join Channel", url=f"https://t.me/{FORCE_JOIN.replace('@','')}")]]
        await update.message.reply_text("❌ Join channel first.", reply_markup=InlineKeyboardMarkup(btn))
        return

    cur.execute("INSERT OR IGNORE INTO users VALUES(?)", (user.id,))
    conn.commit()

    kb = [
        [InlineKeyboardButton("🔥 Viral Videos", callback_data="viral")],
        [InlineKeyboardButton("📺 How to Watch", callback_data="how")],
        [InlineKeyboardButton("🔍 Search Video", callback_data="search")]
    ]

    await update.message.reply_text("🔥 <b>Welcome</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

# ===================== MENU =======================
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "viral":
        kb = [
            [InlineKeyboardButton("📌 Recent Videos", callback_data="recent")],
            [InlineKeyboardButton("📂 All Videos", callback_data="all")]
        ]
        await q.message.reply_text("Choose option:", reply_markup=InlineKeyboardMarkup(kb))

    elif q.data == "how":
        await q.message.reply_text(f"📺 {HOW_TO_WATCH_LINK}")

    elif q.data in ("recent", "all"):
        limit = "LIMIT 10" if q.data == "recent" else ""
        cur.execute(f"""
        SELECT title, link, preview_file_id, preview_type
        FROM videos ORDER BY id DESC {limit}
        """)
        rows = cur.fetchall()
        if not rows:
            await q.message.reply_text("❌ No videos.")
            return

        user_pages[uid] = {"videos": rows, "index": 0}
        await send_card(context.bot, q.message.chat_id, rows[0], 0, len(rows))

    elif q.data == "prev":
        page = user_pages.get(uid)
        if page and page["index"] > 0:
            page["index"] -= 1
            await send_card(context.bot, q.message.chat_id,
                            page["videos"][page["index"]],
                            page["index"], len(page["videos"]))

    elif q.data == "next":
        page = user_pages.get(uid)
        if page and page["index"] < len(page["videos"]) - 1:
            page["index"] += 1
            await send_card(context.bot, q.message.chat_id,
                            page["videos"][page["index"]],
                            page["index"], len(page["videos"]))

    elif q.data == "search":
        user_states[uid] = "search"
        await q.message.reply_text("🔍 Send keyword:")

# ===================== TEXT =======================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    if user_states.get(uid) == "search":
        cur.execute("""
        SELECT title, link, preview_file_id, preview_type
        FROM videos WHERE title LIKE ?
        """, (f"%{text}%",))
        rows = cur.fetchall()
        user_states.pop(uid, None)

        if not rows:
            await update.message.reply_text("❌ No results.")
            return

        user_pages[uid] = {"videos": rows, "index": 0}
        await send_card(context.bot, update.effective_chat.id, rows[0], 0, len(rows))
        return

    if user_states.get(uid) == "title":
        context.user_data["title"] = text
        user_states[uid] = "link"
        await update.message.reply_text("🔗 Send video link")
        return

    if user_states.get(uid) == "link":
        cur.execute("""
        INSERT INTO videos VALUES (NULL,?,?,?,?,?)
        """, (
            context.user_data["title"],
            text,
            context.user_data["preview"],
            context.user_data["type"],
            datetime.now().isoformat()
        ))
        conn.commit()

        await update.message.reply_text("✅ Video added")
        user_states.pop(uid)
        context.user_data.clear()

# ===================== MEDIA ======================
async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if user_states.get(uid) == "preview":
        if update.message.photo:
            context.user_data["preview"] = update.message.photo[-1].file_id
            context.user_data["type"] = "photo"
        elif update.message.video:
            context.user_data["preview"] = update.message.video.file_id
            context.user_data["type"] = "video"

        user_states[uid] = "title"
        await update.message.reply_text("✏️ Send video title")

# ===================== ADMIN ======================
async def addvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    user_states[update.effective_user.id] = "preview"
    await update.message.reply_text("📸 Send preview image/video")

# ===================== MAIN ======================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addvideo", addvideo))
    app.add_handler(CallbackQueryHandler(menu))
    app.add_handler(MessageHandler(filters.TEXT | filters.Entity("url"), text_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, media_handler))

    app.run_polling()

if __name__ == "__main__":
    main()    u = update.effective_user
    await update.message.reply_text(f"Your numeric id: {u.id}\nusername: @{u.username or 'unknown'}")

async def listfiles_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("You are not an admin.")
        return
    cur.execute("SELECT id, file_name, category, is_paid, price, upload_time, uploader_id FROM files ORDER BY id DESC")
    rows = cur.fetchall()
    if not rows:
        await update.message.reply_text("No files uploaded yet.")
        return
    lines = []
    for r in rows:
        lines.append(f"ID:{r[0]} | {r[1]} | Cat:{r[2] or 'Unassigned'} | Paid:{'Yes' if r[3] else 'No'} | Price:{r[4] or '-'} | Uploaded:{r[5]} | By:{r[6]}")
    text = "\n".join(lines)
    chunk = 4000
    for i in range(0, len(text), chunk):
        await update.message.reply_text(text[i:i+chunk])

async def setcat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("You are not an admin.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /setcat <file_id> <cat_key>\nAvailable cat_keys: " + ", ".join(CATEGORIES.keys()))
        return
    try:
        file_id = int(args[0])
    except:
        await update.message.reply_text("file_id must be integer.")
        return
    cat_key = args[1]
    if cat_key not in CATEGORIES:
        await update.message.reply_text("Unknown cat_key. Choices: " + ", ".join(CATEGORIES.keys()))
        return
    label = CATEGORIES[cat_key]
    cur.execute("UPDATE files SET category = ? WHERE id = ?", (label, file_id))
    conn.commit()
    await update.message.reply_text(f"File {file_id} set to category {label}.")

async def removefile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("You are not an admin.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /removefile <file_id>")
        return
    try:
        fid = int(context.args[0])
    except:
        await update.message.reply_text("file_id must be integer.")
        return
    cur.execute("DELETE FROM files WHERE id = ?", (fid,))
    conn.commit()
    await update.message.reply_text(f"Deleted file id {fid} (if existed).")

# =======================
# Admin upload handler (document)
# =======================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = msg.from_user.id
    # If admin is in the middle of paid-QR upload flow (waiting for QR), treat this document as QR image
    if user_id in ADMIN_IDS and context.user_data.get("paid_state") == "waiting_qr" and context.user_data.get("setting_paid_for"):
        # admin is uploading a QR as a document (image file)
        row_id = context.user_data.get("setting_paid_for")
        doc = msg.document
        if not doc:
            await msg.reply_text("Please send the QR image as a photo or an image file (document).")
            return
        qr_file_id = doc.file_id
        price = context.user_data.get("paid_price")
        cur.execute("UPDATE files SET is_paid = 1, price = ?, payment_qr_file_id = ? WHERE id = ?", (price, qr_file_id, row_id))
        conn.commit()
        # clear admin state
        context.user_data.pop("setting_paid_for", None)
        context.user_data.pop("paid_state", None)
        context.user_data.pop("paid_price", None)
        await msg.reply_text(f"✅ Paid file configured (ID {row_id}). Price: {price}. QR uploaded.")
        return

    # Normal admin upload of file to be sold/distributed
    if user_id not in ADMIN_IDS:
        await msg.reply_text("❌ You are not an admin.")
        return

    doc = msg.document
    if not doc:
        await msg.reply_text("Please send a document (not a photo).")
        return

    file_id = doc.file_id
    file_name = doc.file_name or "unnamed"
    upload_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    cur.execute("INSERT INTO files (file_id, file_name, category, is_paid, price, payment_qr_file_id, upload_time, uploader_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (file_id, file_name, "", 0, None, None, upload_time, user_id))
    conn.commit()
    rowid = cur.lastrowid
    logger.info("Admin %s uploaded file %s id %s", user_id, file_name, rowid)
    context.user_data["last_uploaded"] = rowid
    context.user_data["paid_state"] = None
    await msg.reply_text(f"✅ Saved file: {file_name} (ID {rowid}). Choose action:", reply_markup=admin_after_upload_kb(rowid))

# =======================
# Admin photo handler (for QR as photo)
# =======================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = msg.from_user.id
    if user_id in ADMIN_IDS and context.user_data.get("paid_state") == "waiting_qr" and context.user_data.get("setting_paid_for"):
        row_id = context.user_data.get("setting_paid_for")
        photos = msg.photo
        if not photos:
            await msg.reply_text("Please send a photo or an image file as QR.")
            return
        # take highest-resolution photo
        qr_file_id = photos[-1].file_id
        price = context.user_data.get("paid_price")
        cur.execute("UPDATE files SET is_paid = 1, price = ?, payment_qr_file_id = ? WHERE id = ?", (price, qr_file_id, row_id))
        conn.commit()
        # clear state
        context.user_data.pop("setting_paid_for", None)
        context.user_data.pop("paid_state", None)
        context.user_data.pop("paid_price", None)
        await msg.reply_text(f"✅ Paid file configured (ID {row_id}). Price: {price}. QR uploaded.")
        return
    # otherwise ignore photos
    return

# =======================
# Callbacks (browse, download, buy, admin actions)
# =======================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    user_id = query.from_user.id

    # Browse a category
    if data.startswith("browse:"):
        key = data.split(":", 1)[1]
        if key == "paid":
            cur.execute("SELECT id, file_name, price FROM files WHERE is_paid = 1 ORDER BY id DESC")
            rows = cur.fetchall()
            if not rows:
                await query.message.reply_text("No paid files available yet.")
                return
            for r in rows:
                rid, fname, price = r
                await query.message.reply_text(f"📄 {fname}\nID: {rid}\nPrice: {price or 'N/A'}", reply_markup=file_item_kb_for_user(rid, True, price))
            return
        label = CATEGORIES.get(key)
        if not label:
            await query.message.reply_text("Unknown category.")
            return
        cur.execute("SELECT id, file_name, is_paid, price, upload_time FROM files WHERE category = ? ORDER BY id DESC", (label,))
        rows = cur.fetchall()
        if not rows:
            await query.message.reply_text(f"No files in category {label}.")
            return
        for r in rows:
            rid, fname, is_paid, price, uploaded = r
            await query.message.reply_text(
                f"📄 {fname}\nID: {rid}\nPaid: {'Yes' if is_paid else 'No'}\nPrice: {price or '-'}\nUploaded: {uploaded}",
                reply_markup=file_item_kb_for_user(rid, bool(is_paid), price)
            )
        return

    # Download free file
    if data.startswith("dl:"):
        row_id = int(data.split(":", 1)[1])
        missing = []
        if REQUIRED_GROUP:
            ok = await is_member_of(context.bot, REQUIRED_GROUP, user_id)
            if not ok:
                missing.append(("Group", REQUIRED_GROUP))
        if REQUIRED_CHANNEL:
            ok = await is_member_of(context.bot, REQUIRED_CHANNEL, user_id)
            if not ok:
                missing.append(("Channel", REQUIRED_CHANNEL))
        if missing:
            lines = ["❌ To download files you must join:"]
            for kind, ident in missing:
                lines.append(f"• {kind}: {ident} — tap to open")
            kb_rows = []
            join_row = []
            if REQUIRED_GROUP:
                join_row.append(InlineKeyboardButton("Join Group", url=f"https://t.me/{REQUIRED_GROUP.lstrip('@')}"))
            if REQUIRED_CHANNEL:
                join_row.append(InlineKeyboardButton("Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}"))
            if join_row:
                kb_rows.append(join_row)
            kb_rows.append([InlineKeyboardButton("Retry Download", callback_data=f"dl:{row_id}")])
            await query.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb_rows))
            return
        cur.execute("SELECT file_id, file_name FROM files WHERE id = ?", (row_id,))
        r = cur.fetchone()
        if not r:
            await query.message.reply_text("File not found.")
            return
        file_id, fname = r
        try:
            await context.bot.send_document(chat_id=user_id, document=file_id, caption=f"{fname}")
        except Exception as e:
            logger.exception("Failed to send document %s to %s: %s", row_id, user_id, e)
            await query.message.reply_text("Failed to send file — Telegram might have pruned it. Ask admin to re-upload.")
        return

    # Buy flow: create purchase + send admin-uploaded QR
    if data.startswith("buy:"):
        row_id = int(data.split(":", 1)[1])
        cur.execute("SELECT file_name, price, payment_qr_file_id FROM files WHERE id = ?", (row_id,))
        f = cur.fetchone()
        if not f:
            await query.message.reply_text("File not found.")
            return
        fname, price, qr_file_id = f
        requested_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        cur.execute("INSERT INTO purchases (user_id, file_row_id, status, requested_at) VALUES (?, ?, ?, ?)",
                    (user_id, row_id, "pending", requested_at))
        conn.commit()
        purchase_id = cur.lastrowid

        text_msg = f"📄 {fname}\nPrice: {price or 'Contact admin'}\n\nScan the QR uploaded by admin and pay. After payment press 'I paid' to notify admin."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("I paid", callback_data=f"paid_notify:{purchase_id}")]])
        if qr_file_id:
            # Send the QR image (could be photo or document stored as file_id)
            try:
                await context.bot.send_photo(chat_id=user_id, photo=qr_file_id, caption=text_msg, reply_markup=kb)
            except Exception:
                # fallback to sending as document
                try:
                    await context.bot.send_document(chat_id=user_id, document=qr_file_id, caption=text_msg, reply_markup=kb)
                except Exception as e:
                    logger.exception("Failed to send QR for file %s: %s", row_id, e)
                    await query.message.reply_text(text_msg + "\n\n[QR not available due to error — contact admin]", reply_markup=kb)
        else:
            await query.message.reply_text(text_msg + "\n\n[QR not set by admin yet — contact admin]", reply_markup=kb)

        # notify admins
        admin_text = f"🛒 New purchase request #{purchase_id}\nUser: {user_id} (@{query.from_user.username})\nFile: {fname} (id {row_id})\nPrice: {price}\nRequested at: {requested_at}"
        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=aid, text=admin_text, reply_markup=admin_purchase_kb(purchase_id))
            except Exception:
                logger.exception("Failed to notify admin %s about purchase %s", aid, purchase_id)
        return

    # Buyer clicked 'I paid' -> notify admins for verification
    if data.startswith("paid_notify:"):
        purchase_id = int(data.split(":", 1)[1])
        cur.execute("SELECT user_id, file_row_id, requested_at FROM purchases WHERE id = ?", (purchase_id,))
        p = cur.fetchone()
        if not p:
            await query.message.reply_text("Purchase not found.")
            return
        buyer_id, file_row_id, requested_at = p
        cur.execute("SELECT file_name, price FROM files WHERE id = ?", (file_row_id,))
        f = cur.fetchone()
        fname = f[0] if f else "Unknown"
        price = f[1] if f else None
        admin_text = f"💳 Payment claimed for #{purchase_id}\nUser: {buyer_id}\nFile: {fname} (id {file_row_id})\nPrice: {price}\nRequested at: {requested_at}"
        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=aid, text=admin_text, reply_markup=admin_purchase_kb(purchase_id))
            except Exception:
                logger.exception("Failed to notify admin %s about paid_notify %s", aid, purchase_id)
        await query.message.reply_text("✅ Admins notified. They will verify and Approve/Reject.")
        return

    # Admin sets file free (quick)
    if data.startswith("admin_free:"):
        row_id = int(data.split(":", 1)[1])
        if user_id not in ADMIN_IDS:
            await query.message.reply_text("You are not an admin.")
            return
        cur.execute("UPDATE files SET is_paid = 0, price = NULL, payment_qr_file_id = NULL WHERE id = ?", (row_id,))
        conn.commit()
        rows = [[InlineKeyboardButton(label, callback_data=f"admin_setcat:{row_id}:{k}")] for k, label in CATEGORIES.items()]
        await query.message.reply_text("File set to Free. Now choose a category:", reply_markup=InlineKeyboardMarkup(rows))
        return

    # Admin starts setting file as paid: ask price then wait for admin to upload QR (photo or image file)
    if data.startswith("admin_paid:"):
        row_id = int(data.split(":", 1)[1])
        if user_id not in ADMIN_IDS:
            await query.message.reply_text("You are not an admin.")
            return
        context.user_data["setting_paid_for"] = row_id
        context.user_data["paid_state"] = "asking_price"
        await query.message.reply_text("Enter price (e.g. ₹49 or 49):")
        return

    # Admin sets category via inline button after upload
    if data.startswith("admin_setcat:"):
        parts = data.split(":", 2)
        if len(parts) != 3:
            await query.message.reply_text("Invalid command.")
            return
        row_id = int(parts[1])
        cat_key = parts[2]
        if user_id not in ADMIN_IDS:
            await query.message.reply_text("You are not an admin.")
            return
        label = CATEGORIES.get(cat_key)
        if not label:
            await query.message.reply_text("Unknown category key.")
            return
        cur.execute("UPDATE files SET category = ? WHERE id = ?", (label, row_id))
        conn.commit()
        await query.message.reply_text(f"✅ File {row_id} assigned to category {label}.")
        return

    # Admin approve purchase -> send file to buyer
    if data.startswith("approve:"):
        purchase_id = int(data.split(":", 1)[1])
        if user_id not in ADMIN_IDS:
            await query.message.reply_text("You are not an admin.")
            return
        cur.execute("SELECT user_id, file_row_id FROM purchases WHERE id = ?", (purchase_id,))
        p = cur.fetchone()
        if not p:
            await query.message.reply_text("Purchase not found.")
            return
        buyer_id, file_row_id = p
        cur.execute("UPDATE purchases SET status = ? WHERE id = ?", ("approved", purchase_id))
        conn.commit()
        cur.execute("SELECT file_id, file_name FROM files WHERE id = ?", (file_row_id,))
        f = cur.fetchone()
        if not f:
            await query.message.reply_text("File not found.")
            return
        file_id, fname = f
        try:
            await context.bot.send_document(chat_id=buyer_id, document=file_id, caption=f"✅ Purchase #{purchase_id} approved. File: {fname}")
            await query.message.reply_text(f"Approved and sent file to {buyer_id}.")
        except Exception as e:
            logger.exception("Failed to send approved file to buyer %s: %s", buyer_id, e)
            await query.message.reply_text("Approved but failed to send file to buyer (they may need to start the bot).")
        return

    # Admin reject purchase
    if data.startswith("reject:"):
        purchase_id = int(data.split(":", 1)[1])
        if user_id not in ADMIN_IDS:
            await query.message.reply_text("You are not an admin.")
            return
        cur.execute("SELECT user_id FROM purchases WHERE id = ?", (purchase_id,))
        p = cur.fetchone()
        if not p:
            await query.message.reply_text("Purchase not found.")
            return
        buyer_id = p[0]
        cur.execute("UPDATE purchases SET status = ? WHERE id = ?", ("rejected", purchase_id))
        conn.commit()
        try:
            await context.bot.send_message(chat_id=buyer_id, text=f"❌ Your purchase #{purchase_id} was rejected by admin.")
            await query.message.reply_text("Purchase rejected and user notified.")
        except Exception:
            logger.exception("Failed to notify buyer about rejection.")
            await query.message.reply_text("Rejected but failed to notify buyer.")
        return

    await query.message.reply_text("Unknown action or expired button.")

# =======================
# Text handler for admin flows (price)
# =======================
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    if user_id in ADMIN_IDS and context.user_data.get("paid_state") == "asking_price" and context.user_data.get("setting_paid_for"):
        row_id = context.user_data.get("setting_paid_for")
        context.user_data["paid_price"] = text
        context.user_data["paid_state"] = "waiting_qr"
        await update.message.reply_text("Got price. Now please *upload the payment QR image* (send as photo or image file).", parse_mode="Markdown")
        return
    # otherwise ignore text
    return

# =======================
# Main
# =======================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("listfiles", listfiles_cmd))
    app.add_handler(CommandHandler("setcat", setcat_cmd))
    app.add_handler(CommandHandler("removefile", removefile_cmd))

    # Document handler (admin uploads file OR admin uploads QR as document)
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    # Photo handler (admin uploads QR as photo)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_message_handler))

    logger.info("File Store Bot (QR-paid) starting...")
    app.run_polling(allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    main()
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
    from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()

