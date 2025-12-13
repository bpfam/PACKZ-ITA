# =====================================================
# PACKZ-ITA BOT — FULL STABLE
# MENU + CONTATTI + VETRINA
# INLINE KEYBOARD FIX iOS
# =====================================================

import os
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_FILE   = os.environ.get("DB_FILE", "/var/data/users.db")

PHOTO_URL = os.environ.get(
    "PHOTO_URL",
    "https://i.postimg.cc/bv4ssL2t/2A3BDCFD-2D21-41BC-8BFA-9C5D238E5C3B.jpg"
)

WELCOME_TEXT = os.environ.get(
    "WELCOME_TEXT",
    "🔥 **PACKZ-ITA UFFICIALE** 🇮🇹🇪🇸\n\n"
    "Qualità reale. Zero chiacchiere.\n"
    "Solo contatti verificati.\n\n"
    "👇 Usa i tasti sotto"
)

MENU_TEXT = os.environ.get(
    "MENU_PAGE_TEXT",
    "📖 **MENÙ PACKZ-ITA**\n\n• Prodotto A\n• Prodotto B\n• Prodotto C"
)

INFO_TEXT = os.environ.get(
    "INFO_PAGE_TEXT",
    "📲 **CONTATTI PACKZ-ITA**\n\nTelegram ufficiale\nDisponibilità limitata"
)

VETRINA_URL = os.environ.get(
    "VETRINA_URL",
    "https://bpfam.github.io/PACKZ-ITA/index.html"
)

# ---------------- LOG ----------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("PACKZ-ITA")

# ---------------- DB ----------------
def init_db():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            first_seen TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_user(uid: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users VALUES (?, ?)",
        (uid, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()

# ---------------- KEYBOARD ----------------
def kb_home():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 MENÙ", callback_data="MENU"),
            InlineKeyboardButton("📲 CONTATTI", callback_data="INFO")
        ],
        [
            InlineKeyboardButton("🎥 VETRINA", url=VETRINA_URL)
        ]
    ])

def kb_back():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Indietro", callback_data="HOME")]
    ])

# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if user:
        save_user(user.id)

    # 🔥 FOTO + TESTO + TASTI (UN SOLO MESSAGGIO)
    await chat.send_photo(
        photo=PHOTO_URL,
        caption=WELCOME_TEXT,
        reply_markup=kb_home()
    )

# ---------------- BUTTONS ----------------
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "MENU":
        await q.message.edit_caption(
            caption=MENU_TEXT,
            reply_markup=kb_back()
        )

    elif q.data == "INFO":
        await q.message.edit_caption(
            caption=INFO_TEXT,
            reply_markup=kb_back()
        )

    elif q.data == "HOME":
        await q.message.edit_caption(
            caption=WELCOME_TEXT,
            reply_markup=kb_home()
        )

# ---------------- MAIN ----------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN mancante")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))

    log.info("✅ PACKZ-ITA BOT AVVIATO")
    app.run_polling()

if __name__ == "__main__":
    main()