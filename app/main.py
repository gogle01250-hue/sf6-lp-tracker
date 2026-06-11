from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import psycopg2, psycopg2.extras, json, os

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

# ── API ──────────────────────────────────────────────────
@app.get("/api/records")
def get_records():
    return JSONResponse(kv_get("records", []))

@app.put("/api/records")
async def put_records(request: Request):
    body = await request.json()
    kv_set("records", body)
    return {"ok": True}

@app.get("/api/char_lp_memory")
def get_char_lp_memory():
    return JSONResponse(kv_get("char_lp_memory", {}))

@app.put("/api/char_lp_memory")
async def put_char_lp_memory(request: Request):
    body = await request.json()
    kv_set("char_lp_memory", body)
    return {"ok": True}

@app.get("/api/combos")
def get_combos():
    return JSONResponse(kv_get("combos", []))

@app.put("/api/combos")
async def put_combos(request: Request):
    body = await request.json()
    kv_set("combos", body)
    return {"ok": True}

# ── Static files (index.html) ────────────────────────────
app.mount("/", StaticFiles(directory="/app/static", html=True), name="static")
