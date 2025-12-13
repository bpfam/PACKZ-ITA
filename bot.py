# =====================================================
# PACKZ ITA BOT — FULL STABLE
# MENÙ / CONTATTI / VETRINA
# =====================================================

import os
import logging
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_FILE = os.environ.get("DB_FILE", "/var/data/users.db")

PHOTO_URL = os.environ.get(
    "PHOTO_URL",
    "https://TUO_LINK_LOGO.jpg"
)

WELCOME_TEXT = os.environ.get(
    "WELCOME_TEXT",
    "🔥 PACKZ ITA 🇮🇹🇪🇸\n\n"
    "Qualità. Serietà. Continuità.\n\n"
    "Usa i pulsanti qui sotto 👇"
)

MENU_TEXT = os.environ.get(
    "MENU_TEXT",
    "📖 MENÙ PACKZ ITA\n\n"
    "• Disponibilità aggiornate\n"
    "• Qualità top\n"
    "• Contattaci per info"
)

CONTACTS_TEXT = os.environ.get(
    "CONTACTS_TEXT",
    "📲 CONTATTI PACKZ ITA\n\n"
    "Telegram: @packzita\n"
    "Supporto diretto"
)

VETRINA_URL = os.environ.get(
    "VETRINA_URL",
    "https://tuosito.github.io/vetrina.html"
)

# ---------------- LOG ----------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("packz-ita")

# ---------------- DB ----------------
def init_db():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_seen TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_user(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, first_seen) VALUES (?, ?)",
        (user_id, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()

# ---------------- KEYBOARDS ----------------
def kb_home():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 MENÙ", callback_data="MENU"),
            InlineKeyboardButton("📲 CONTATTI", callback_data="CONTACTS"),
        ],
        [
            InlineKeyboardButton("🎥 VETRINA", url=VETRINA_URL)
        ]
    ])

def kb_back():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Indietro", callback_data="HOME")]
    ])

# ---------------- HANDLERS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    save_user(user.id)

    await chat.send_photo(
        photo=PHOTO_URL
    )

    await chat.send_message(
        text=WELCOME_TEXT,
        reply_markup=kb_home()
    )

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "MENU":
        await q.message.edit_text(
            MENU_TEXT,
            reply_markup=kb_back()
        )

    elif q.data == "CONTACTS":
        await q.message.edit_text(
            CONTACTS_TEXT,
            reply_markup=kb_back()
        )

    elif q.data == "HOME":
        await q.message.edit_text(
            WELCOME_TEXT,
            reply_markup=kb_home()
        )

# ---------------- MAIN ----------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN mancante")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button))

    log.info("✅ PACKZ ITA BOT AVVIATO")
    app.run_polling()

if __name__ == "__main__":
    main()