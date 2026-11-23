"""Tiny SQLite cache shared by all MCP servers."""
import json, sqlite3, time
from pathlib import Path

DB = Path(__file__).resolve().parent / "data" / "cache.sqlite"
DB.parent.mkdir(exist_ok=True)

def _conn():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT, ts REAL)")
    return c

def get(key, max_age_s=7 * 86400):
    with _conn() as c:
        row = c.execute("SELECT v, ts FROM cache WHERE k=?", (key,)).fetchone()
    if row and time.time() - row[1] < max_age_s:
        return json.loads(row[0])
    return None

def put(key, value):
    with _conn() as c:
        c.execute("REPLACE INTO cache VALUES (?, ?, ?)", (key, json.dumps(value), time.time()))
