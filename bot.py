# =====================================================
# PACKZ-ITA BOT — FULL v1.7
# PROTECT + PIN + BROADCAST_DELETE
# - MENÙ, CONTATTI, VETRINA
# - /status, /utenti, /backup, /restore_db
# - /broadcast + /broadcast_delete
# =====================================================

import os, csv, shutil, logging, sqlite3, asyncio as aio
from pathlib import Path
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import RetryAfter, Forbidden, BadRequest, NetworkError

VERSION = "PACKZ-ITA-FULL-1.7-NO-STATS"

# ---------------- LOG ----------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("packz-ita")

# ---------------- ENV ----------------
BOT_TOKEN   = os.environ.get("BOT_TOKEN", "")
DB_FILE     = os.environ.get("DB_FILE", "/var/data/users.db")
BACKUP_DIR  = os.environ.get("BACKUP_DIR", "/var/data/backup")

PHOTO_URL = os.environ.get("PHOTO_URL", "")

WELCOME_TEXT = os.environ.get(
    "WELCOME_TEXT",
    "ＰＡＣＫＺ－ＩＴＡ\nＯＦＦＩＣＩＡＬ 🇪🇸🇮🇹\n\nBenvenuto nel bot ufficiale."
)

MENU_PAGE_TEXT = os.environ.get("MENU_PAGE_TEXT", "📖 MENÙ")
INFO_PAGE_TEXT = os.environ.get("INFO_PAGE_TEXT", "📲 CONTATTI")

VETRINA_URL = os.environ.get("VETRINA_URL", "")

# ---------------- ADMIN ----------------
def build_admin_ids() -> set[int]:
    ids = set()
    raw = os.environ.get("ADMIN_IDS", "").replace(" ", "")
    if raw:
        for x in raw.split(","):
            if x.isdigit():
                ids.add(int(x))
    return ids

ADMIN_IDS = build_admin_ids()

def is_admin(uid: int | None) -> bool:
    if not ADMIN_IDS:
        return True
    return uid in ADMIN_IDS if uid else False

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
        )
    """)
    conn.commit()
    conn.close()

def upsert_user(u):
    if not u:
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cur.execute("SELECT 1 FROM users WHERE user_id=?", (u.id,))
    if cur.fetchone():
        cur.execute("""
            UPDATE users
            SET username=?, first_name=?, last_name=?, last_seen=?
            WHERE user_id=?
        """, (u.username, u.first_name, u.last_name, now, u.id))
    else:
        cur.execute("""
            INSERT INTO users
            VALUES (?,?,?,?,?,?)
        """, (u.id, u.username, u.first_name, u.last_name, now, now))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def is_sqlite_db(path: str):
    try:
        with open(path, "rb") as f:
            return f.read(16) == b"SQLite format 3\x00", "OK"
    except:
        return False, "File non valido"

# ---------------- TASTIERA ----------------
def kb_home():
    rows = [
        [
            InlineKeyboardButton("📖 MENÙ", callback_data="MENU"),
            InlineKeyboardButton("📲 CONTATTI", callback_data="INFO"),
        ]
    ]
    if VETRINA_URL:
        rows.append([InlineKeyboardButton("🎥 VETRINA", url=VETRINA_URL)])
    return InlineKeyboardMarkup(rows)

def kb_back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Indietro", callback_data="HOME")]])

# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    chat = update.effective_chat
    if u:
        upsert_user(u)

    if PHOTO_URL:
        try:
            await chat.send_photo(PHOTO_URL, protect_content=True)
        except:
            pass

    await chat.send_message(
        WELCOME_TEXT,
        reply_markup=kb_home(),
        protect_content=True
    )

# ---------------- BOTTONI ----------------
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "MENU":
        await q.message.edit_text(MENU_PAGE_TEXT, reply_markup=kb_back())
    elif q.data == "INFO":
        await q.message.edit_text(INFO_PAGE_TEXT, reply_markup=kb_back())
    elif q.data == "HOME":
        await q.message.edit_text(WELCOME_TEXT, reply_markup=kb_home())

# ---------------- ADMIN ----------------
async def utenti_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    users = get_all_users()
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    path = Path(BACKUP_DIR) / "users.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(users[0].keys() if users else [])
        for u in users:
            w.writerow(u.values())
    await update.message.reply_document(InputFile(path))

# ---------------- MAIN ----------------
def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN mancante")

    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(CommandHandler("utenti", utenti_cmd))

    log.info("✅ BOT AVVIATO — %s", VERSION)
    app.run_polling()

if __name__ == "__main__":
    main()