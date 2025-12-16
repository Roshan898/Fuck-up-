#!/usr/bin/env python3
import os
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
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ========= CONFIG (ENV ONLY) =========
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
FORCE_JOIN = os.environ.get("FORCE_JOIN")
HOW_TO_WATCH_LINK = os.environ.get("HOW_TO_WATCH_LINK", "https://t.me/")
# ====================================

logging.basicConfig(level=logging.INFO)

# ========= DATABASE =========
conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
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

# ========= STATE =========
user_states = {}
user_pages = {}

# ========= FORCE JOIN =========
async def is_joined(bot, uid):
    if not FORCE_JOIN:
        return True
    try:
        m = await bot.get_chat_member(FORCE_JOIN, uid)
        return m.status in ("member", "administrator", "creator")
    except:
        return False

# ========= SEND CARD =========
async def send_card(bot, chat_id, video, index, total):
    title, link, fid, ftype = video
    caption = f"<b>{title}</b>\n🔗 {link}\n\n{index+1}/{total}"

    buttons = []
    if index > 0:
        buttons.append(InlineKeyboardButton("⬅ Prev", callback_data="prev"))
    if index < total - 1:
        buttons.append(InlineKeyboardButton("Next ➡", callback_data="next"))

    markup = InlineKeyboardMarkup([buttons]) if buttons else None

    if ftype == "photo":
        await bot.send_photo(chat_id, fid, caption=caption, parse_mode="HTML", reply_markup=markup)
    elif ftype == "video":
        await bot.send_video(chat_id, fid, caption=caption, parse_mode="HTML", reply_markup=markup)
    else:
        await bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=markup)

# ========= START =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not await is_joined(context.bot, uid):
        await update.message.reply_text("❌ Join channel first")
        return

    cur.execute("INSERT OR IGNORE INTO users VALUES(?)", (uid,))
    conn.commit()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Videos", callback_data="videos")],
        [InlineKeyboardButton("📺 How to Watch", callback_data="how")]
    ])

    await update.message.reply_text("🔥 <b>Welcome</b>", reply_markup=kb, parse_mode="HTML")

# ========= MENU =========
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "videos":
        cur.execute("SELECT title, link, preview_file_id, preview_type FROM videos ORDER BY id DESC LIMIT 5")
        rows = cur.fetchall()
        if not rows:
            await q.message.reply_text("No videos")
            return
        user_pages[uid] = {"videos": rows, "index": 0}
        await send_card(context.bot, q.message.chat_id, rows[0], 0, len(rows))

    elif q.data == "prev":
        p = user_pages.get(uid)
        if p and p["index"] > 0:
            p["index"] -= 1
            await send_card(context.bot, q.message.chat_id, p["videos"][p["index"]], p["index"], len(p["videos"]))

    elif q.data == "next":
        p = user_pages.get(uid)
        if p and p["index"] < len(p["videos"]) - 1:
            p["index"] += 1
            await send_card(context.bot, q.message.chat_id, p["videos"][p["index"]], p["index"], len(p["videos"]))

    elif q.data == "how":
        await q.message.reply_text(HOW_TO_WATCH_LINK)

# ========= ADMIN =========
async def addvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    user_states[ADMIN_ID] = "preview"
    await update.message.reply_text("Send preview image or video")

async def media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if user_states.get(ADMIN_ID) != "preview":
        return

    if update.message.photo:
        context.user_data["preview"] = update.message.photo[-1].file_id
        context.user_data["type"] = "photo"
    elif update.message.video:
        context.user_data["preview"] = update.message.video.file_id
        context.user_data["type"] = "video"

    user_states[ADMIN_ID] = "title"
    await update.message.reply_text("Send title")

async def text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    step = user_states.get(ADMIN_ID)

    if step == "title":
        context.user_data["title"] = update.message.text
        user_states[ADMIN_ID] = "link"
        await update.message.reply_text("Send link")

    elif step == "link":
        cur.execute("""
        INSERT INTO videos(title, link, preview_file_id, preview_type, created_at)
        VALUES (?,?,?,?,?)
        """, (
            context.user_data["title"],
            update.message.text,
            context.user_data["preview"],
            context.user_data["type"],
            datetime.now().isoformat()
        ))
        conn.commit()
        user_states.pop(ADMIN_ID, None)
        context.user_data.clear()
        await update.message.reply_text("✅ Video added")

# ========= MAIN =========
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addvideo", addvideo))
    app.add_handler(CallbackQueryHandler(menu))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, media))
    app.add_handler(MessageHandler(filters.TEXT | filters.Entity("url"), text))

    app.run_polling()

if __name__ == "__main__":
    main()
