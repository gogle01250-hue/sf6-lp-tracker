from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import psycopg2, psycopg2.extras, json, os, re

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

# ── ルームID バリデーション ──────────────────────────────
ROOM_RE = re.compile(r'^[a-zA-Z0-9_\-]{1,32}$')

def room_key(room: str, kind: str) -> str:
    """room:kind 形式のKVキーを返す。不正なルームIDは拒否。"""
    if not ROOM_RE.match(room):
        raise ValueError(f"Invalid room id: {room!r}")
    return f"{room}:{kind}"

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

# ── Static files (index.html) ────────────────────────────
app.mount("/", StaticFiles(directory="/app/static", html=True), name="static")
