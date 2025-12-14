# =====================================================
# PACKZ-ITA BOT — PRO v2.0 (STABLE)
# - Menu + Contatti + Vetrina
# - Admin: /whoami /status /utenti /backup /restore_db
# - Broadcast + Broadcast_delete
# - Restore DB compatibile con DB di altri bot (colonne diverse)
# =====================================================

import os, csv, shutil, logging, sqlite3, asyncio as aio
from pathlib import Path
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import RetryAfter, Forbidden, BadRequest, NetworkError

VERSION = "PACKZ-ITA-PRO-2.0"

# ---------------- LOG ----------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("packz-ita")

# ---------------- ENV ----------------
BOT_TOKEN  = os.environ.get("BOT_TOKEN", "").strip()
DB_FILE    = os.environ.get("DB_FILE", "/var/data/users.db").strip()
BACKUP_DIR = os.environ.get("BACKUP_DIR", "/var/data/backup").strip()

PHOTO_URL   = os.environ.get("PHOTO_URL", "").strip()
VETRINA_URL = os.environ.get("VETRINA_URL", "").strip()

WELCOME_TEXT   = os.environ.get("WELCOME_TEXT", "ＰＡＣＫＺ－ＩＴＡ\nＯＦＦＩＣＩＡＬ 🇪🇸🇮🇹").strip()
MENU_PAGE_TEXT = os.environ.get("MENU_PAGE_TEXT", "📖 MENÙ PACKZ-ITA").strip()
INFO_PAGE_TEXT = os.environ.get("INFO_PAGE_TEXT", "📲 CONTATTI PACKZ-ITA").strip()

# ---------------- ADMIN ----------------
def build_admin_ids() -> set[int]:
    raw = os.environ.get("ADMIN_IDS", "").replace(" ", "")
    ids: set[int] = set()
    if raw:
        for x in raw.split(","):
            if x.isdigit():
                ids.add(int(x))
    return ids

ADMIN_IDS = build_admin_ids()
log.info("ADMIN_IDS=%s", ADMIN_IDS)

def is_admin(uid: int | None) -> bool:
    # Se ADMIN_IDS vuoto => tutti admin (comodo nei test)
    if not ADMIN_IDS:
        return True
    return bool(uid) and uid in ADMIN_IDS

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
            INSERT INTO users(user_id,username,first_name,last_name,first_seen,last_seen)
            VALUES(?,?,?,?,?,?)
        """, (u.id, u.username, u.first_name, u.last_name, now, now))
    conn.commit()
    conn.close()

def count_users() -> int:
    conn = sqlite3.connect(DB_FILE)
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return n

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM users ORDER BY first_seen ASC")]
    conn.close()
    return rows

def is_sqlite_db(path: str):
    p = Path(path)
    if not p.exists():
        return False, "Il file non esiste"
    try:
        with open(p, "rb") as f:
            header = f.read(16)
        if header != b"SQLite format 3\x00":
            return False, "Header SQLite mancante"
        conn = sqlite3.connect(path)
        conn.execute("SELECT 1")
        conn.close()
        return True, "OK"
    except Exception as e:
        return False, f"Errore lettura: {e}"

def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cols = set()
    for r in conn.execute(f"PRAGMA table_info({table})").fetchall():
        cols.add(r[1])
    return cols

# ---------------- TASTIERA ----------------
def kb_home():
    rows = [[
        InlineKeyboardButton("📖 MENÙ", callback_data="MENU"),
        InlineKeyboardButton("📲 CONTATTI", callback_data="INFO"),
    ]]
    # Vetrina SOLO se c'è il link
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
        except Exception as e:
            log.warning("Errore invio foto: %s", e)

    await chat.send_message(
        WELCOME_TEXT,
        reply_markup=kb_home(),
        protect_content=True
    )

    # pin iscritti
    try:
        stats = await chat.send_message(f"👥 Iscritti PACKZ-ITA {count_users()}", protect_content=True)
        await context.bot.pin_chat_message(chat.id, stats.message_id, disable_notification=True)
    except Exception:
        pass

# ---------------- CALLBACK ----------------
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    if q.data == "MENU":
        await q.message.edit_text(MENU_PAGE_TEXT, reply_markup=kb_back())
    elif q.data == "INFO":
        await q.message.edit_text(INFO_PAGE_TEXT, reply_markup=kb_back())
    elif q.data == "HOME":
        await q.message.edit_text(WELCOME_TEXT, reply_markup=kb_home())

# ---------------- ADMIN UTILS ----------------
async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    await update.effective_message.reply_text(
        f"🆔 Il tuo ID: {uid}\nADMIN_IDS attuali: {sorted(list(ADMIN_IDS))}",
        protect_content=True
    )

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.effective_message.reply_text(
        f"✅ Online {VERSION}\n"
        f"👥 Utenti: {count_users()}\n"
        f"DB: {DB_FILE}\nBackup: {BACKUP_DIR}\n"
        f"VETRINA_URL: {'SET' if bool(VETRINA_URL) else 'VUOTO'}",
        protect_content=True
    )

async def utenti_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    users = get_all_users()
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    csv_path = Path(BACKUP_DIR) / f"users_{stamp}.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id","username","first_name","last_name","first_seen","last_seen"])
        for u in users:
            w.writerow([
                u.get("user_id",""),
                u.get("username") or "",
                u.get("first_name") or "",
                u.get("last_name") or "",
                u.get("first_seen") or "",
                u.get("last_seen") or "",
            ])

    await update.effective_message.reply_text(f"👥 Utenti totali: {len(users)}", protect_content=True)
    with open(csv_path, "rb") as fh:
        await update.effective_message.reply_document(
            document=InputFile(fh, filename=csv_path.name),
            protect_content=True
        )

async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    ok, why = is_sqlite_db(DB_FILE)
    if not ok:
        await update.effective_message.reply_text(f"⚠️ DB non valido: {why}", protect_content=True)
        return

    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = Path(BACKUP_DIR) / f"backup_{stamp}.db"
    shutil.copy2(DB_FILE, out)

    with open(out, "rb") as fh:
        await update.effective_message.reply_document(
            document=InputFile(fh, filename=out.name),
            caption="✅ Backup pronto da scaricare"
        )

# ---------------- RESTORE DB (COMPATIBILE CON DB DIVERSI) ----------------
async def restore_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    msg = update.effective_message
    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.reply_text("✅ Per ripristinare: rispondi a un file .db con /restore_db", protect_content=True)
        return

    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    tmp = Path(BACKUP_DIR) / f"import_{msg.reply_to_message.document.file_unique_id}.db"

    tg_file = await msg.reply_to_message.document.get_file()
    await tg_file.download_to_drive(custom_path=str(tmp))

    ok, why = is_sqlite_db(str(tmp))
    if not ok:
        await msg.reply_text(f"❌ File non valido: {why}", protect_content=True)
        tmp.unlink(missing_ok=True)
        return

    imp = sqlite3.connect(tmp)
    imp.row_factory = sqlite3.Row

    # tabella users esiste?
    t = imp.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    if not t:
        imp.close()
        tmp.unlink(missing_ok=True)
        await msg.reply_text("❌ Nel DB importato manca la tabella 'users'", protect_content=True)
        return

    imp_cols = table_columns(imp, "users")

    # mapping colonne alternative
    def pick(row, *names, default=None):
        for n in names:
            if n in row.keys() and row[n] is not None:
                return row[n]
        return default

    rows = imp.execute("SELECT * FROM users").fetchall()
    imp.close()

    main = sqlite3.connect(DB_FILE)
    main.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        first_seen TEXT,
        last_seen TEXT
    )""")

    now = datetime.now(timezone.utc).isoformat()

    sql = """
    INSERT INTO users (user_id, username, first_name, last_name, first_seen, last_seen)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(user_id) DO UPDATE SET
        username   = excluded.username,
        first_name = excluded.first_name,
        last_name  = excluded.last_name,
        last_seen  = excluded.last_seen
    """

    merged = 0
    for r in rows:
        # alcuni DB vecchi hanno firstseen/lastseen o solo last_seen ecc.
        user_id = pick(r, "user_id", "id")
        if user_id is None:
            continue

        username   = pick(r, "username", "user", default=None)
        first_name = pick(r, "first_name", "firstname", default=None)
        last_name  = pick(r, "last_name", "lastname", default=None)
        first_seen = pick(r, "first_seen", "firstseen", "firstSeen", default=now)
        last_seen  = pick(r, "last_seen", "lastseen", "lastSeen", default=now)

        main.execute(sql, (user_id, username, first_name, last_name, first_seen, last_seen))
        merged += 1

    main.commit()
    main.close()
    tmp.unlink(missing_ok=True)

    await msg.reply_text(f"✅ Restore completato (importati/aggiornati: {merged})", protect_content=True)

# ---------------- BROADCAST + DELETE ----------------
LAST_BROADCAST: dict[int, int] = {}

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    m = update.effective_message
    users = get_all_users()
    total = len(users)
    if total == 0:
        await m.reply_text("Nessun utente nel DB.", protect_content=True)
        return

    mode = "text"
    text_body = None

    if m.reply_to_message:
        mode = "copy"
        preview = m.reply_to_message.text or m.reply_to_message.caption or "(media)"
    else:
        text_body = " ".join(context.args) if context.args else None
        if not text_body:
            await m.reply_text("Uso: /broadcast <testo> oppure reply a un contenuto con /broadcast", protect_content=True)
            return
        preview = text_body[:120] + ("…" if len(text_body) > 120 else "")

    info = await m.reply_text(f"📣 Broadcast iniziato\nUtenti: {total}\nAnteprima: {preview}", protect_content=True)
    LAST_BROADCAST.clear()

    sent = blocked = failed = 0
    for u in users:
        chat_id = u["user_id"]
        try:
            if mode == "copy" and m.reply_to_message:
                out = await m.reply_to_message.copy(chat_id=chat_id, protect_content=True)
            else:
                out = await context.bot.send_message(chat_id=chat_id, text=text_body, protect_content=True)
            LAST_BROADCAST[chat_id] = out.message_id
            sent += 1
        except Forbidden:
            blocked += 1
        except RetryAfter as e:
            await aio.sleep(e.retry_after + 1)
            try:
                if mode == "copy" and m.reply_to_message:
                    out = await m.reply_to_message.copy(chat_id=chat_id, protect_content=True)
                else:
                    out = await context.bot.send_message(chat_id=chat_id, text=text_body, protect_content=True)
                LAST_BROADCAST[chat_id] = out.message_id
                sent += 1
            except Exception:
                failed += 1
        except (BadRequest, NetworkError, Exception):
            failed += 1

        await aio.sleep(0.05)

    await info.edit_text(
        f"✅ Broadcast finito\nTotali: {total}\nInviati: {sent}\nBloccati: {blocked}\nErrori: {failed}",
        protect_content=True
    )

async def broadcast_delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not LAST_BROADCAST:
        await update.effective_message.reply_text("❌ Nessun broadcast recente da cancellare (o bot riavviato).", protect_content=True)
        return

    ok = err = 0
    for chat_id, msg_id in list(LAST_BROADCAST.items()):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            ok += 1
        except (Forbidden, BadRequest):
            err += 1
        except RetryAfter as e:
            await aio.sleep(e.retry_after + 1)
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                ok += 1
            except Exception:
                err += 1
        except Exception:
            err += 1
        await aio.sleep(0.05)

    LAST_BROADCAST.clear()
    await update.effective_message.reply_text(f"🧹 Broadcast cancellato.\n✅ Eliminati: {ok}\n⚠️ Errori: {err}", protect_content=True)

# ---------------- MAIN ----------------
def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN mancante")

    init_db()
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button))

    # admin
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("utenti", utenti_cmd))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("restore_db", restore_db))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("broadcast_delete", broadcast_delete_cmd))

    log.info("✅ BOT AVVIATO — %s", VERSION)
    app.run_polling()

if __name__ == "__main__":
    main()