# =====================================================
# PACKZ-ITA BOT — FULL v1.8
# - Testi da file texts.json (niente limiti Render)
# - /restore_db SMART: importa DB anche con colonne diverse
# - 3 bottoni: MENÙ, CONTATTI, VETRINA (+ Indietro)
# - /status, /utenti (CSV), /backup, /restore_db (MERGE)
# - /broadcast (testo o copia in reply)
# - /broadcast_delete (ultimo broadcast finché non riavvii)
# - protect_content=True su tutto (tranne file backup)
# =====================================================

import os, csv, shutil, logging, sqlite3, asyncio as aio, json
from pathlib import Path
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import RetryAfter, Forbidden, BadRequest, NetworkError

VERSION = "PACKZ-ITA-FULL-1.8-TEXTS-JSON-RESTORE-SMART"

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
PHOTO_URL   = os.environ.get("PHOTO_URL", "")
VETRINA_URL = os.environ.get("VETRINA_URL", "")

# File testi (nel repo, stessa cartella di bot.py)
TEXTS_FILE  = os.environ.get("TEXTS_FILE", "texts.json")

# ---------------- ADMIN ----------------
def build_admin_ids() -> set[int]:
    ids: set[int] = set()
    raw = os.environ.get("ADMIN_IDS", "").replace(" ", "")
    if raw:
        for x in raw.split(","):
            if x.isdigit():
                ids.add(int(x))
    return ids

ADMIN_IDS = build_admin_ids()
log.info("ADMIN_IDS: %s", ADMIN_IDS)

def is_admin(uid: int | None) -> bool:
    if not ADMIN_IDS:
        return True
    return bool(uid) and uid in ADMIN_IDS

# ---------------- TEXTS (da file) ----------------
DEFAULT_TEXTS = {
    "welcome": "🔥 PACKZ-ITA OFFICIAL 🇮🇹🇪🇸\n\nUsa i pulsanti qui sotto 👇",
    "menu": "📖 MENÙ PACKZ-ITA\n• Voce A\n• Voce B\n• Voce C",
    "info": "📲 CONTATTI & INFO — PACKZ-ITA\n\n(aggiungi qui i contatti)"
}

def load_texts() -> dict:
    # Prova a leggere texts.json. Se manca o è rotto → usa default.
    try:
        p = Path(TEXTS_FILE)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            out = dict(DEFAULT_TEXTS)
            for k in ("welcome", "menu", "info"):
                if isinstance(data.get(k), str) and data.get(k).strip():
                    out[k] = data[k]
            return out
    except Exception as e:
        log.warning("texts.json non valido: %s", e)
    return dict(DEFAULT_TEXTS)

TEXTS = load_texts()

def WELCOME_TEXT(): return TEXTS["welcome"]
def MENU_PAGE_TEXT(): return TEXTS["menu"]
def INFO_PAGE_TEXT(): return TEXTS["info"]

# ---------------- DB ----------------
BASE_COLUMNS = [
    ("user_id", "INTEGER PRIMARY KEY"),
    ("username", "TEXT"),
    ("first_name", "TEXT"),
    ("last_name", "TEXT"),
    ("first_seen", "TEXT"),
    ("last_seen", "TEXT"),
]

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

def ensure_columns(conn: sqlite3.Connection):
    # aggiunge colonne mancanti (per compatibilità)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    existing = {row[1] for row in cur.fetchall()}  # row[1] = name
    for name, decl in BASE_COLUMNS:
        if name not in existing:
            try:
                cur.execute(f"ALTER TABLE users ADD COLUMN {name} {decl}")
            except Exception:
                pass
    conn.commit()

def upsert_user(u):
    if not u:
        return
    conn = sqlite3.connect(DB_FILE)
    ensure_columns(conn)
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
        INSERT INTO users(user_id, username, first_name, last_name, first_seen, last_seen)
        VALUES(?,?,?,?,?,?)
        """, (u.id, u.username, u.first_name, u.last_name, now, now))

    conn.commit()
    conn.close()

def count_users():
    conn = sqlite3.connect(DB_FILE)
    ensure_columns(conn)
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return n

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    ensure_columns(conn)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY COALESCE(first_seen, last_seen) ASC")
    rows = [dict(r) for r in cur.fetchall()]
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

def users_columns(conn: sqlite3.Connection) -> list[str]:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    return [r[1] for r in cur.fetchall()]

def pick(colset: set[str], *names: str) -> str | None:
    for n in names:
        if n in colset:
            return n
    return None

# ---------------- TASTIERA (INLINE) ----------------
def kb_home():
    row1 = [
        InlineKeyboardButton("📖 MENÙ", callback_data="MENU"),
        InlineKeyboardButton("📲 CONTATTI", callback_data="INFO"),
    ]
    rows = [row1]

    # Vetrina: se VETRINA_URL non è impostato, non mostra il tasto
    if VETRINA_URL and VETRINA_URL.strip():
        rows.append([InlineKeyboardButton("🎥 VETRINA", url=VETRINA_URL.strip())])

    return InlineKeyboardMarkup(rows)

def kb_back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Indietro", callback_data="HOME")]])

# ---------------- START + PIN AUTO ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    chat = update.effective_chat
    if u:
        upsert_user(u)

    # ricarica testi ad ogni /start (così se cambi texts.json si aggiorna)
    global TEXTS
    TEXTS = load_texts()

    # foto logo (se c'è)
    if PHOTO_URL and PHOTO_URL.strip():
        try:
            await chat.send_photo(PHOTO_URL.strip(), protect_content=True)
        except Exception as e:
            log.warning("Errore invio foto: %s", e)

    # welcome + bottoni
    try:
        await chat.send_message(
            WELCOME_TEXT(),
            reply_markup=kb_home(),
            protect_content=True
        )
    except Exception as e:
        log.warning("Errore invio welcome: %s", e)

    # pin conteggio
    try:
        total = count_users()
        stats_msg = await chat.send_message(
            f"👥 Iscritti PACKZ-ITA {total}",
            protect_content=True
        )
        try:
            await context.bot.pin_chat_message(
                chat_id=chat.id,
                message_id=stats_msg.message_id,
                disable_notification=True
            )
        except Exception as e:
            log.warning("Errore pin messaggio stats: %s", e)
    except Exception as e:
        log.warning("Errore invio stats: %s", e)

# ---------------- BOTTONI ----------------
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    # ricarica testi (se li aggiorni)
    global TEXTS
    TEXTS = load_texts()

    if q.data == "MENU":
        await q.message.edit_text(MENU_PAGE_TEXT(), reply_markup=kb_back())
    elif q.data == "INFO":
        await q.message.edit_text(INFO_PAGE_TEXT(), reply_markup=kb_back())
    elif q.data == "HOME":
        await q.message.edit_text(WELCOME_TEXT(), reply_markup=kb_home())

# ---------------- ADMIN ----------------
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        f"✅ Online v{VERSION}\n"
        f"👥 Utenti: {count_users()}\n"
        f"DB: {DB_FILE}\n"
        f"Backup dir: {BACKUP_DIR}\n"
        f"Vetrina: {VETRINA_URL or '(non impostata)'}",
        protect_content=True
    )

async def utenti_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    users = get_all_users()
    n = len(users)

    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    csv_path = Path(BACKUP_DIR) / f"users_{stamp}.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "username", "first_name", "last_name", "first_seen", "last_seen"])
        for u in users:
            w.writerow([
                u.get("user_id", ""),
                u.get("username") or "",
                u.get("first_name") or "",
                u.get("last_name") or "",
                u.get("first_seen") or "",
                u.get("last_seen") or "",
            ])

    await update.message.reply_text(f"👥 Utenti totali: {n}", protect_content=True)

    with open(csv_path, "rb") as fh:
        await update.message.reply_document(
            document=InputFile(fh, filename=csv_path.name),
            protect_content=True
        )

async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    ok, why = is_sqlite_db(DB_FILE)
    if not ok:
        await update.message.reply_text(f"⚠️ DB non valido: {why}", protect_content=True)
        return

    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    db_out  = Path(BACKUP_DIR) / f"backup_{stamp}.db"

    shutil.copy2(DB_FILE, db_out)

    with open(db_out, "rb") as fh:
        await update.message.reply_document(
            document=InputFile(fh, filename=db_out.name),
            caption="✅ Backup pronto da scaricare"
        )

# ---------------- RESTORE_DB (SMART) ----------------
async def restore_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    msg = update.effective_message
    if not msg.reply_to_message or not msg.reply_to_message.document:
        await update.message.reply_text(
            "Per ripristinare: rispondi a un file .db con /restore_db",
            protect_content=True
        )
        return

    doc = msg.reply_to_message.document
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    tmp = Path(BACKUP_DIR) / f"restore_{doc.file_unique_id}.db"

    tg_file = await doc.get_file()
    await tg_file.download_to_drive(custom_path=str(tmp))

    ok, why = is_sqlite_db(str(tmp))
    if not ok:
        await update.message.reply_text(f"❌ Il file non è un DB SQLite valido: {why}", protect_content=True)
        tmp.unlink(missing_ok=True)
        return

    try:
        main = sqlite3.connect(DB_FILE)
        ensure_columns(main)

        imp  = sqlite3.connect(tmp)

        # controlla tabella users
        try:
            imp.execute("SELECT 1 FROM users LIMIT 1")
        except Exception:
            await update.message.reply_text("❌ Nel DB importato non esiste la tabella 'users'.", protect_content=True)
            imp.close()
            main.close()
            tmp.unlink(missing_ok=True)
            return

        cols = users_columns(imp)
        colset = set(cols)

        c_user_id   = pick(colset, "user_id", "id", "chat_id", "telegram_id")
        c_username  = pick(colset, "username", "user_name", "nick")
        c_firstname = pick(colset, "first_name", "firstname", "name", "first")
        c_lastname  = pick(colset, "last_name", "lastname", "surname", "last")
        c_firstseen = pick(colset, "first_seen", "firstseen", "created_at", "joined_at", "first_time")
        c_lastseen  = pick(colset, "last_seen", "lastseen", "updated_at", "last_time", "last_active")

        if not c_user_id:
            await update.message.reply_text("❌ Nel DB importato non trovo una colonna ID utente.", protect_content=True)
            imp.close()
            main.close()
            tmp.unlink(missing_ok=True)
            return

        select_cols = [c_user_id, c_username, c_firstname, c_lastname, c_firstseen, c_lastseen]
        select_cols = [c for c in select_cols if c is not None]

        rows = imp.execute(
            f"SELECT {', '.join(select_cols)} FROM users"
        ).fetchall()

        now = datetime.now(timezone.utc).isoformat()

        def row_get(r, idx_map, key):
            i = idx_map.get(key)
            return r[i] if i is not None else None

        idx_map = {name: i for i, name in enumerate(select_cols)}

        out_rows = []
        for r in rows:
            user_id = row_get(r, idx_map, c_user_id)
            if user_id is None:
                continue

            username  = row_get(r, idx_map, c_username)  if c_username  else None
            first_name= row_get(r, idx_map, c_firstname) if c_firstname else None
            last_name = row_get(r, idx_map, c_lastname)  if c_lastname  else None
            first_seen= row_get(r, idx_map, c_firstseen) if c_firstseen else None
            last_seen = row_get(r, idx_map, c_lastseen)  if c_lastseen  else None

            # fallback se mancano
            if not first_seen:
                first_seen = now
            if not last_seen:
                last_seen = now

            out_rows.append((int(user_id), username, first_name, last_name, first_seen, last_seen))

        sql = """
        INSERT INTO users (user_id, username, first_name, last_name, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username   = excluded.username,
            first_name = excluded.first_name,
            last_name  = excluded.last_name,
            last_seen  = excluded.last_seen
        """
        main.executemany(sql, out_rows)
        main.commit()

        await update.message.reply_text(
            f"✅ Restore completato\nImportati/Mergiati: {len(out_rows)} utenti",
            protect_content=True
        )

        imp.close()
        main.close()
        tmp.unlink(missing_ok=True)

    except Exception as e:
        log.exception("Errore restore_db")
        await update.message.reply_text(f"❌ Errore restore: {e}", protect_content=True)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass

# ---------------- BROADCAST + DELETE ----------------
LAST_BROADCAST: dict[int, int] = {}  # chat_id -> message_id

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    m = update.effective_message
    users = get_all_users()
    total = len(users)
    if total == 0:
        await m.reply_text("Nessun utente nel DB.", protect_content=True)
        return

    text_body = None
    mode = "text"
    if m.reply_to_message:
        mode = "copy"
        text_preview = (m.reply_to_message.text or m.reply_to_message.caption or "(media)")
    else:
        text_body = " ".join(context.args) if context.args else None
        if not text_body:
            await m.reply_text("Uso: /broadcast <testo> oppure in reply a un contenuto /broadcast", protect_content=True)
            return
        text_preview = (text_body[:120] + "…") if len(text_body) > 120 else text_body

    sent = blocked = failed = 0
    info_msg = await m.reply_text(
        f"📣 Broadcast iniziato\nUtenti: {total}\nAnteprima: {text_preview}",
        protect_content=True
    )

    LAST_BROADCAST.clear()

    for u in users:
        chat_id = u["user_id"]
        try:
            if mode == "copy" and m.reply_to_message:
                msg_out = await m.reply_to_message.copy(chat_id=chat_id, protect_content=True)
            else:
                msg_out = await context.bot.send_message(chat_id=chat_id, text=text_body, protect_content=True)
            LAST_BROADCAST[chat_id] = msg_out.message_id
            sent += 1
        except Forbidden:
            blocked += 1
        except RetryAfter as e:
            await aio.sleep(e.retry_after + 1)
            try:
                if mode == "copy" and m.reply_to_message:
                    msg_out = await m.reply_to_message.copy(chat_id=chat_id, protect_content=True)
                else:
                    msg_out = await context.bot.send_message(chat_id=chat_id, text=text_body, protect_content=True)
                LAST_BROADCAST[chat_id] = msg_out.message_id
                sent += 1
            except Exception:
                failed += 1
        except (BadRequest, NetworkError, Exception):
            failed += 1

        await aio.sleep(0.05)

    await info_msg.edit_text(
        f"✅ Broadcast finito\nTotali: {total}\nInviati: {sent}\nBloccati: {blocked}\nErrori: {failed}",
        protect_content=True
    )

async def broadcast_delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not LAST_BROADCAST:
        await update.message.reply_text(
            "❌ Nessun broadcast recente da cancellare (o bot riavviato).",
            protect_content=True
        )
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

    await update.message.reply_text(
        f"🧹 Broadcast cancellato.\n✅ Eliminati: {ok}\n⚠️ Errori: {err}",
        protect_content=True
    )

# ---------------- MAIN ----------------
def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN mancante")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button))

    app.add_handler(CommandHandler("status",           status_cmd))
    app.add_handler(CommandHandler("utenti",           utenti_cmd))
    app.add_handler(CommandHandler("backup",           backup_cmd))
    app.add_handler(CommandHandler("restore_db",       restore_db))
    app.add_handler(CommandHandler("broadcast",        broadcast_cmd))
    app.add_handler(CommandHandler("broadcast_delete", broadcast_delete_cmd))

    log.info("✅ BOT AVVIATO — %s", VERSION)
    app.run_polling()

if __name__ == "__main__":
    main()