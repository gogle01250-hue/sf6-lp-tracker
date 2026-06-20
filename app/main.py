from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import psycopg2, psycopg2.extras, json, os, re, secrets, string

DATABASE_URL = os.environ["DATABASE_URL"]

app = FastAPI()

# ── DB接続 ────────────────────────────────────────────────
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kv (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rooms (
                    name       TEXT PRIMARY KEY,
                    password   TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
        conn.commit()

init_db()

# ── KV helpers ───────────────────────────────────────────
def kv_get(key: str, default):
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT value FROM kv WHERE key=%s", (key,))
            row = cur.fetchone()
            return json.loads(row["value"]) if row else default

def kv_set(key: str, value):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kv(key,value) VALUES(%s,%s)
                ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value
                """,
                (key, json.dumps(value, ensure_ascii=False))
            )
        conn.commit()

# ── パスワード生成 ────────────────────────────────────────
def generate_password() -> str:
    """ランダム12文字英数字（XXXX-XXXX-XXXX形式）"""
    chars = string.ascii_uppercase + string.digits
    groups = [''.join(secrets.choice(chars) for _ in range(4)) for _ in range(3)]
    return '-'.join(groups)

# ── ルームID バリデーション ──────────────────────────────
ROOM_RE = re.compile(r'^[^\s:/\\]{1,32}$')

def room_key(room: str, kind: str) -> str:
    if not ROOM_RE.match(room):
        raise ValueError(f"Invalid room id: {room!r}")
    return f"{room}:{kind}"

# ── 認証API ──────────────────────────────────────────────
@app.post("/api/auth/register")
async def register(request: Request):
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name or not ROOM_RE.match(name):
        return JSONResponse({"ok": False, "error": "IDが無効です（1〜32文字、スペース・コロン・スラッシュ不可）"}, status_code=400)
    password = generate_password()
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO rooms(name, password) VALUES(%s, %s)",
                    (name, password)
                )
            conn.commit()
        return JSONResponse({"ok": True, "password": password})
    except psycopg2.errors.UniqueViolation:
        return JSONResponse({"ok": False, "error": "このIDは既に使用されています"}, status_code=409)

@app.post("/api/auth/login")
async def login(request: Request):
    body = await request.json()
    name = (body.get("name") or "").strip()
    password = (body.get("password") or "").strip()
    if not name or not password:
        return JSONResponse({"ok": False, "error": "IDとパスワードを入力してください"}, status_code=400)
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT password FROM rooms WHERE name=%s", (name,))
            row = cur.fetchone()
    if not row or row["password"] != password:
        return JSONResponse({"ok": False, "error": "IDまたはパスワードが違います"}, status_code=401)
    return JSONResponse({"ok": True})

@app.post("/api/auth/change-password")
async def change_password(request: Request):
    body = await request.json()
    name         = (body.get("name") or "").strip()
    new_password = (body.get("new_password") or "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "ルームIDが不明です"}, status_code=400)
    if len(new_password) < 5:
        return JSONResponse({"ok": False, "error": "パスワードは5文字以上で入力してください"}, status_code=400)
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT name FROM rooms WHERE name=%s", (name,))
            if not cur.fetchone():
                return JSONResponse({"ok": False, "error": "ルームが見つかりません"}, status_code=404)
            cur.execute("UPDATE rooms SET password=%s WHERE name=%s", (new_password, name))
    return JSONResponse({"ok": True})

# ── API (ルームスコープ) ──────────────────────────────────
@app.get("/api/{room}/records")
def get_records(room: str):
    return JSONResponse(kv_get(room_key(room, "records"), []))

@app.put("/api/{room}/records")
async def put_records(room: str, request: Request):
    body = await request.json()
    kv_set(room_key(room, "records"), body)
    return {"ok": True}

@app.get("/api/{room}/char_lp_memory")
def get_char_lp_memory(room: str):
    return JSONResponse(kv_get(room_key(room, "char_lp_memory"), {}))

@app.put("/api/{room}/char_lp_memory")
async def put_char_lp_memory(room: str, request: Request):
    body = await request.json()
    kv_set(room_key(room, "char_lp_memory"), body)
    return {"ok": True}

@app.get("/api/{room}/combos")
def get_combos(room: str):
    return JSONResponse(kv_get(room_key(room, "combos"), []))

@app.put("/api/{room}/combos")
async def put_combos(room: str, request: Request):
    body = await request.json()
    kv_set(room_key(room, "combos"), body)
    return {"ok": True}

@app.post("/api/{room}/combos")
async def post_combos(room: str, request: Request):
    """sendBeacon 用（beforeunload から POST で呼ばれる）"""
    try:
        body = await request.json()
        kv_set(room_key(room, "combos"), body)
    except Exception:
        pass
    return {"ok": True}

@app.get("/api/{room}/notes")
def get_notes(room: str):
    return JSONResponse(kv_get(room_key(room, "notes"), []))

@app.put("/api/{room}/notes")
async def put_notes(room: str, request: Request):
    body = await request.json()
    kv_set(room_key(room, "notes"), body)
    return {"ok": True}

@app.post("/api/{room}/notes")
async def post_notes(room: str, request: Request):
    """sendBeacon 用（beforeunload から POST で呼ばれる）"""
    try:
        body = await request.json()
        kv_set(room_key(room, "notes"), body)
    except Exception:
        pass
    return {"ok": True}

# ── 管理者設定 ────────────────────────────────────────────
ADMIN_ID       = os.environ.get("ADMIN_ID", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "01250")

def verify_admin(body: dict) -> bool:
    return (body.get("admin_id") == ADMIN_ID and
            body.get("admin_password") == ADMIN_PASSWORD)

# ── 管理者API ─────────────────────────────────────────────
from fastapi.responses import FileResponse, HTMLResponse

@app.get("/admin")
def admin_page():
    return FileResponse("/app/static/admin.html")

@app.post("/api/admin/login")
async def admin_login(request: Request):
    body = await request.json()
    if not verify_admin(body):
        return JSONResponse({"ok": False, "error": "IDまたはパスワードが違います"}, status_code=401)
    return JSONResponse({"ok": True})

@app.post("/api/admin/users")
async def admin_get_users(request: Request):
    body = await request.json()
    if not verify_admin(body):
        return JSONResponse({"ok": False, "error": "認証エラー"}, status_code=401)
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT name, password, created_at FROM rooms ORDER BY created_at DESC")
            rows = cur.fetchall()
    users = [{"name": r["name"], "password": r["password"],
              "created_at": r["created_at"].strftime("%Y/%m/%d %H:%M") if r["created_at"] else "—"}
             for r in rows]
    return JSONResponse({"ok": True, "users": users})

@app.post("/api/admin/reset-password")
async def admin_reset_password(request: Request):
    body = await request.json()
    if not verify_admin(body):
        return JSONResponse({"ok": False, "error": "認証エラー"}, status_code=401)
    target_name  = (body.get("target_name") or "").strip()
    new_password = (body.get("new_password") or "").strip()
    if not target_name:
        return JSONResponse({"ok": False, "error": "対象ユーザーIDが不明です"}, status_code=400)
    if len(new_password) < 5:
        return JSONResponse({"ok": False, "error": "パスワードは5文字以上にしてください"}, status_code=400)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE rooms SET password=%s WHERE name=%s", (new_password, target_name))
            if cur.rowcount == 0:
                return JSONResponse({"ok": False, "error": "ユーザーが見つかりません"}, status_code=404)
        conn.commit()
    return JSONResponse({"ok": True})

@app.post("/api/admin/delete-room")
async def admin_delete_room(request: Request):
    body = await request.json()
    if not verify_admin(body):
        return JSONResponse({"ok": False, "error": "認証エラー"}, status_code=401)
    target_name = (body.get("target_name") or "").strip()
    if not target_name:
        return JSONResponse({"ok": False, "error": "対象ユーザーIDが不明です"}, status_code=400)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rooms WHERE name=%s", (target_name,))
            deleted = cur.rowcount
        conn.commit()
    if deleted == 0:
        return JSONResponse({"ok": False, "error": "ユーザーが見つかりません"}, status_code=404)
    return JSONResponse({"ok": True})

# ── Mobile route ────────────────────────────────────────
@app.get("/mobile")
def mobile():
    return FileResponse("/app/static/index_mobile.html")

# ── Static files (index.html) ────────────────────────────
app.mount("/", StaticFiles(directory="/app/static", html=True), name="static")
