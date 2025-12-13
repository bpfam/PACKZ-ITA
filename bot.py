# =====================================================
# PACKZ-ITA BOT — FULL STABLE
# MENU / CONTATTI / VETRINA SEMPRE VISIBILI
# NO PIN — NO BUG — RENDER READY
# =====================================================

import os, logging, sqlite3
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
BOT_TOKEN  = os.environ.get("BOT_TOKEN")
DB_FILE    = os.environ.get("DB_FILE", "/var/data/users.db")

PHOTO_URL = os.environ.get(
    "PHOTO_URL",
    "METTI_QUI_LA_TUA_PHOTO_URL"
)

WELCOME_TEXT = os.environ.get(
    "WELCOME_TEXT",
    "🔥 PACKZ-ITA 🔥\n\n"
    "Benvenuto nel bot ufficiale.\n"
    "Usa i pulsanti qui sotto ⬇️"
)

MENU_PAGE_TEXT = os.environ.get(
    "MENU_PAGE_TEXT",
    "📖 MENÙ PACKZ-ITA\n\n"
    "• Voce 1\n"
    "• Voce 2\n"
    "• Voce 3"
)

INFO_PAGE_TEXT = os.environ.get(
    "INFO_PAGE_TEXT",
    "📲 CONTATTI PACKZ-ITA\n\n"
    "Telegram: @packzita\n"
    "Instagram: @packz_ita"
)

VETRINA_URL = os.environ.get(
    "VETRINA_URL",
    "https://bpfam.github.io/PACKZ-ITA/"
)

# ---------------- LOG ----------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("packz-ita")

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

def save_user(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users VALUES (?, ?)",
                (user_id, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

# ---------------- KEYBOARD ----------------
def kb_home():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 MENÙ", callback_data="MENU"),
            InlineKeyboardButton("📲 CONTATTI", callback_data="INFO"),
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

    await chat.send_photo(PHOTO_URL)
    await chat.send_message(
        WELCOME_TEXT,
        reply_markup=kb_home()
    )

# ---------------- BUTTONS ----------------
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "MENU":
        await q.message.edit_text(MENU_PAGE_TEXT, reply_markup=kb_back())

    elif q.data == "INFO":
        await q.message.edit_text(INFO_PAGE_TEXT, reply_markup=kb_back())

    elif q.data == "HOME":
        await q.message.edit_text(WELCOME_TEXT, reply_markup=kb_home())

# ---------------- MAIN ----------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN mancante")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button))

    log.info("✅ PACKZ-ITA BOT ONLINE")
    app.run_polling()

if __name__ == "__main__":
    main()