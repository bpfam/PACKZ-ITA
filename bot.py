# =====================================================
# PACKZ-ITA BOT — FULL v1.8 STABLE
# - NO testo hardcoded
# - WELCOME_TEXT solo da variabile
# - restore_db compatibile con DB diversi
# =====================================================

import os, csv, shutil, logging, sqlite3, asyncio as aio
from pathlib import Path
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)
from telegram.error import RetryAfter, Forbidden, BadRequest

VERSION = "PACKZ-ITA-1.8-STABLE"

# ---------------- LOG ----------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("packz-ita")

# ---------------- ENV ----------------
BOT_TOKEN  = os.environ.get("BOT_TOKEN", "")
DB_FILE    = os.environ.get("DB_FILE", "/var/data/users.db")
BACKUP_DIR = os.environ.get("BACKUP_DIR", "/var/data/backup")

PHOTO_URL = os.environ.get("PHOTO_URL", "").strip()
VETRINA_URL = os.environ.get("VETRINA_URL", "").strip()

WELCOME_TEXT = os.environ.get("WELCOME_TEXT", "").strip()
if not WELCOME_TEXT:
    WELCOME_TEXT = "ＰＡＣＫＺ－ＩＴＡ\nＯＦＦＩＣＩＡＬ 🇪🇸🇮🇹"

MENU_PAGE_TEXT = os.environ.get("MENU_PAGE_TEXT", "📖 MENÙ PACKZ-ITA")
INFO_PAGE_TEXT = os.environ.get("INFO_PAGE_TEXT", "📲 CONTATTI PACKZ-ITA")

# ---------------- ADMIN ----------------
def build_admin_ids():
    raw = os.environ.get("ADMIN_IDS", "")
    return {int(x) for x in raw.replace(" ", "").split(",") if x.isdigit()}

ADMIN_IDS = build_admin_ids()

def is_admin(uid):
    return not ADMIN_IDS or uid in ADMIN_IDS

# ---------------- DB ----------------
def init_db():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        first_seen TEXT,
        last_seen TEXT
    )""")
    conn.commit()
    conn.close()

def upsert_user(u):
    if not u:
        return
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE user_id=?", (u.id,))
    if cur.fetchone():
        cur.execute("""
            UPDATE users SET username=?, first_name=?, last_name=?, last_seen=?
            WHERE user_id=?
        """, (u.username, u.first_name, u.last_name, now, u.id))
    else:
        cur.execute("""
            INSERT INTO users VALUES (?,?,?,?,?,?)
        """, (u.id, u.username, u.first_name, u.last_name, now, now))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM users")]
    conn.close()
    return rows

def count_users():
    conn = sqlite3.connect(DB_FILE)
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return n

# ---------------- TASTI ----------------
def kb_home():
    rows = [[
        InlineKeyboardButton("📖 MENÙ", callback_data="MENU"),
        InlineKeyboardButton("📲 CONTATTI", callback_data="INFO"),
    ]]
    if VETRINA_URL:
        rows.append([InlineKeyboardButton("🎥 VETRINA", url=VETRINA_URL)])
    return InlineKeyboardMarkup(rows)

def kb_back():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Indietro", callback_data="HOME")]
    ])

# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    chat = update.effective_chat
    if u:
        upsert_user(u)

    if PHOTO_URL:
        try:
            await chat.send_photo(PHOTO_URL, protect_content=True)
        except Exception as e:
            log.warning(f"Foto errore: {e}")

    await chat.send_message(
        WELCOME_TEXT,
        reply_markup=kb_home(),
        protect_content=True
    )

    try:
        stats = await chat.send_message(
            f"👥 Iscritti PACKZ-ITA {count_users()}",
            protect_content=True
        )
        await context.bot.pin_chat_message(
            chat.id, stats.message_id, disable_notification=True
        )
    except Exception:
        pass

# ---------------- CALLBACK ----------------
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "MENU":
        await q.message.edit_text(MENU_PAGE_TEXT, reply_markup=kb_back())
    elif q.data == "INFO":
        await q.message.edit_text(INFO_PAGE_TEXT, reply_markup=kb_back())
    elif q.data == "HOME":
        await q.message.edit_text(WELCOME_TEXT, reply_markup=kb_home())

# ---------------- RESTORE DB (COMPATIBILE) ----------------
async def restore_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    msg = update.effective_message
    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.reply_text("Rispondi a un file .db con /restore_db")
        return

    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    tmp = Path(BACKUP_DIR) / "import.db"

    file = await msg.reply_to_message.document.get_file()
    await file.download_to_drive(tmp)

    imp = sqlite3.connect(tmp)
    imp.row_factory = sqlite3.Row
    rows = imp.execute("SELECT * FROM users").fetchall()
    imp.close()

    main = sqlite3.connect(DB_FILE)
    for r in rows:
        main.execute("""
            INSERT OR IGNORE INTO users(user_id,username,first_name,last_name,first_seen,last_seen)
            VALUES (?,?,?,?,?,?)
        """, (
            r.get("user_id"),
            r.get("username"),
            r.get("first_name"),
            r.get("last_name"),
            r.get("first_seen") or datetime.now(timezone.utc).isoformat(),
            r.get("last_seen") or datetime.now(timezone.utc).isoformat(),
        ))
    main.commit()
    main.close()
    tmp.unlink(missing_ok=True)

    await msg.reply_text("✅ Restore completato")

# ---------------- MAIN ----------------
def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN mancante")

    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(CommandHandler("restore_db", restore_db))

    log.info("BOT AVVIATO %s", VERSION)
    app.run_polling()

if __name__ == "__main__":
    main()