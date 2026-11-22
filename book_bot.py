import asyncio
import json
import os
import sqlite3
from aiohttp import web

BOT_TOKEN = os.getenv("BOT_TOKEN", "9258461014:AAGwAjRgy3RBqHKuGdahhJhgrbRTPQkm-xE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8292187188"))
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = "library.db"

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            banned INTEGER DEFAULT 0
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            url TEXT NOT NULL
        )
        """
    )
    cur.execute("SELECT COUNT(*) FROM books")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO books (title, author, url) VALUES (?, ?, ?)",
            [
                ("مقدمة ابن خلدون", "ابن خلدون", "https://www.gutenberg.org/"),
                ("كليلة ودمنة", "ابن المقفع", "https://www.gutenberg.org/"),
                ("النظرات", "مصطفى لطفي المنفلوطي", "https://www.gutenberg.org/"),
            ],
        )
    conn.commit()
    conn.close()


def register_user(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, banned) VALUES (?, 0)", (user_id,))
    cur.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.commit()
    conn.close()
    return not (row and row[0] == 1)


def set_ban(user_id: int, banned: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, banned) VALUES (?, ?)", (user_id, banned))
    cur.execute("UPDATE users SET banned = ? WHERE user_id = ?", (banned, user_id))
    conn.commit()
    conn.close()


def get_stats():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM books")
    books_count = cur.fetchone()[0]
    conn.close()
    return users_count, books_count


def add_book(title: str, author: str, url: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO books (title, author, url) VALUES (?, ?, ?)", (title, author, url))
    conn.commit()
    conn.close()


def search_books(query: str):
    q = f"%{query.strip()}%"
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, author, url FROM books WHERE title LIKE ? OR author LIKE ? ORDER BY id DESC",
        (q, q),
    )
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "author": r[2], "url": r[3]} for r in rows]


def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE banned = 0")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


async def send_message(session: web.ClientSession, chat_id: int, text: str, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with session.post(f"{TELEGRAM_API}/sendMessage", json=payload) as resp:
        return await resp.json()


MINI_APP_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>مكتبة الكتب</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    body { font-family: Tahoma, Arial, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 16px; }
    .box { max-width: 600px; margin: auto; background: #1e293b; border-radius: 12px; padding: 16px; }
    input { width: 100%; box-sizing: border-box; padding: 10px; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: #fff; margin-bottom: 12px; }
    .book { background: #334155; padding: 12px; border-radius: 8px; margin-bottom: 10px; }
    .book-title { font-weight: bold; font-size: 16px; margin-bottom: 4px; }
    .book-author { color: #cbd5e1; font-size: 13px; margin-bottom: 8px; }
    a.btn { display: inline-block; background: #2563eb; color: #fff; text-decoration: none; padding: 6px 12px; border-radius: 6px; font-size: 13px; }
  </style>
</head>
<body>
  <div class="box">
    <h2>البحث في المكتبة</h2>
    <input id="q" type="text" placeholder="ابحث باسم الكتاب أو المؤلف..." oninput="runSearch()" />
    <div id="results"></div>
  </div>
  <script>
    const tg = window.Telegram && window.Telegram.WebApp;
    if (tg) { tg.ready(); tg.expand(); }
    async function runSearch() {
      const q = document.getElementById('q').value;
      const res = await fetch('/api/books?q=' + encodeURIComponent(q));
      const data = await res.json();
      const container = document.getElementById('results');
      if (!data.books.length) {
        container.innerHTML = '<p>لا توجد نتائج مطابقة.</p>';
        return;
      }
      container.innerHTML = data.books.map(b => `
        <div class="book">
          <div class="book-title">${escapeHtml(b.title)}</div>
          <div class="book-author">المؤلف: ${escapeHtml(b.author)}</div>
          <a class="btn" href="${escapeAttr(b.url)}" target="_blank" rel="noopener">فتح / تحميل</a>
        </div>
      `).join('');
    }
    function escapeHtml(s) {
      return String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
    }
    function escapeAttr(s) {
      return String(s).replace(/"/g, '&quot;');
    }
    runSearch();
  </script>
</body>
</html>
"""


async def handle_miniapp(request: web.Request):
    return web.Response(text=MINI_APP_HTML, content_type="text/html")


async def handle_api_books(request: web.Request):
    q = request.query.get("q", "")
    books = search_books(q)
    return web.json_response({"books": books})


async def handle_update(session: web.ClientSession, update: dict):
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    chat = msg.get("chat", {})
    user = msg.get("from", {})
    chat_id = chat.get("id")
    user_id = user.get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not user_id or not text:
        return

    if user_id != ADMIN_ID and not register_user(user_id):
        await send_message(session, chat_id, "عذراً، حسابك محظور من استخدام البوت.")
        return
    register_user(user_id)

    if text == "/start":
        keyboard = None
        if BASE_URL.startswith("https://"):
            keyboard = {
                "keyboard": [[{"text": "فتح مكتبة الكتب", "web_app": {"url": f"{BASE_URL}/app"}}]],
                "resize_keyboard": True,
            }
        note = "" if BASE_URL.startswith("https://") else "\n\nملاحظة: عيّن BASE_URL برابط https لتفعيل زر التطبيق المصغر."
        await send_message(session, chat_id, f"أهلاً بك في بوت المكتبة.{note}", reply_markup=keyboard)
        return

    if text.startswith("/search"):
        query = text[len("/search"):].strip()
        books = search_books(query)
        if not books:
            await send_message(session, chat_id, "لم يتم العثور على كتب مطابقة.")
            return
        lines = [f"• <b>{b['title']}</b> — {b['author']}\n{b['url']}" for b in books[:10]]
        await send_message(session, chat_id, "\n\n".join(lines))
        return

    if user_id == ADMIN_ID:
        if text == "/admin":
            await send_message(
                session,
                chat_id,
                "<b>أوامر الأدمن:</b>\n"
                "/stats — إحصائيات المستخدمين والكتب\n"
                "/addbook العنوان | المؤلف | الرابط\n"
                "/broadcast الرسالة — إرسال إذاعة لجميع المستخدمين\n"
                "/ban ID — حظر مستخدم\n"
                "/unban ID — فك حظر مستخدم",
            )
            return
        if text == "/stats":
            users_count, books_count = get_stats()
            await send_message(session, chat_id, f"المستخدمون: <b>{users_count}</b>\nالكتب: <b>{books_count}</b>")
            return
        if text.startswith("/addbook "):
            parts = [p.strip() for p in text[len("/addbook "):].split("|")]
            if len(parts) == 3 and all(parts):
                add_book(parts[0], parts[1], parts[2])
                await send_message(session, chat_id, "تمت إضافة الكتاب بنجاح.")
            else:
                await send_message(session, chat_id, "الصيغة: /addbook العنوان | المؤلف | الرابط")
            return
        if text.startswith("/broadcast "):
            bcast = text[len("/broadcast "):].strip()
            if bcast:
                users = get_all_users()
                sent = 0
                for uid in users:
                    res = await send_message(session, uid, bcast)
                    if res.get("ok"):
                        sent += 1
                await send_message(session, chat_id, f"تم الإرسال إلى {sent} مستخدم.")
            return
        if text.startswith("/ban "):
            try:
                target = int(text.split()[1])
                set_ban(target, 1)
                await send_message(session, chat_id, f"تم حظر المستخدم {target}.")
            except Exception:
                await send_message(session, chat_id, "الصيغة: /ban ID")
            return
        if text.startswith("/unban "):
            try:
                target = int(text.split()[1])
                set_ban(target, 0)
                await send_message(session, chat_id, f"تم فك الحظر عن المستخدم {target}.")
            except Exception:
                await send_message(session, chat_id, "الصيغة: /unban ID")
            return

    books = search_books(text)
    if books:
        lines = [f"• <b>{b['title']}</b> — {b['author']}\n{b['url']}" for b in books[:8]]
        await send_message(session, chat_id, "\n\n".join(lines))
    else:
        await send_message(session, chat_id, "اكتب اسم كتاب أو مؤلف للبحث، أو أرسل /start.")


async def poll_telegram(app: web.Application):
    offset = 0
    async with web.ClientSession() as session:
        while True:
            try:
                params = {"timeout": 25, "offset": offset}
                async with session.get(f"{TELEGRAM_API}/getUpdates", params=params, timeout=35) as resp:
                    data = await resp.json()
                if data.get("ok"):
                    for upd in data.get("result", []):
                        offset = max(offset, upd["update_id"] + 1)
                        asyncio.create_task(handle_update(session, upd))
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(3)


async def start_background_tasks(app: web.Application):
    app["poller"] = asyncio.create_task(poll_telegram(app))


async def cleanup_background_tasks(app: web.Application):
    app["poller"].cancel()
    await asyncio.gather(app["poller"], return_exceptions=True)


def create_app() -> web.Application:
    init_db()
    app = web.Application()
    app.router.add_get("/", handle_miniapp)
    app.router.add_get("/app", handle_miniapp)
    app.router.add_get("/api/books", handle_api_books)
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=PORT)

