"""SQLite storage. One file in the data folder; nothing leaves this PC."""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

HOME = Path(os.environ.get("CLAIMSCOUT_HOME", Path.home() / ".local/share/claimscout"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS settlements (
    id TEXT PRIMARY KEY,          -- source:slug
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,                     -- where we read it
    summary TEXT,
    eligibility TEXT,
    award TEXT,
    proof TEXT,                   -- the listing's own words about proof
    proof_needed INTEGER,         -- 1 yes, 0 no, NULL unknown
    claim_url TEXT,               -- the administrator's claim form
    website TEXT,
    deadline TEXT,                -- ISO date
    case_name TEXT,
    states TEXT,                  -- JSON list of US state codes the class is limited to ([] = nationwide/unknown)
    published TEXT,
    fetched_at REAL
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS matches (
    settlement_id TEXT PRIMARY KEY,
    score REAL, verdict TEXT, reason TEXT, method TEXT,
    proof_plan TEXT,              -- JSON: what the phone should search mail for
    updated_at REAL, seen INTEGER DEFAULT 0, dismissed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS proofs (
    id INTEGER PRIMARY KEY,
    settlement_id TEXT, account TEXT, message_id TEXT,
    sender TEXT, subject TEXT, date TEXT,
    kind TEXT, amount TEXT, order_number TEXT, summary TEXT,
    created_at REAL,
    UNIQUE (settlement_id, account, message_id)
);
CREATE TABLE IF NOT EXISTS answers (
    settlement_id TEXT PRIMARY KEY,
    answer TEXT,                  -- yes | no | unsure | unused (didn't pick the company at all)
    at REAL
);
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY,
    settlement_id TEXT UNIQUE,
    status TEXT,                  -- filed | approved | paid | denied
    claim_number TEXT, filed_at TEXT, expected TEXT, paid TEXT, notes TEXT,
    updated_at REAL
);
"""

SETTLEMENT_FIELDS = ["id", "source", "title", "url", "summary", "eligibility", "award", "proof", "proof_needed",
                     "claim_url", "website", "deadline", "case_name", "states", "published"]


class DB:
    def __init__(self, path=None):
        path = Path(path or HOME / "claimscout.db")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            have = {r[1] for r in self.conn.execute("PRAGMA table_info(settlements)")}
            # questionnaire fields, filled by questions.py (rules first, AI later); not touched by refreshes
            for col in ("label TEXT", "category TEXT", "question TEXT", "enriched INTEGER DEFAULT 0"):
                if col.split()[0] not in have:
                    self.conn.execute(f"ALTER TABLE settlements ADD COLUMN {col}")
            self.conn.commit()

    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def x(self, sql, args=()):
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur

    # --- key/value (profile, AI settings, pairing) ---
    def get(self, key, default=None):
        rows = self.q("SELECT value FROM kv WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def put(self, key, value):
        self.x("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, json.dumps(value)))

    # --- settlements ---
    def upsert_settlement(self, s: dict) -> bool:
        """Insert or refresh a listing. Returns True when it is new."""
        new = not self.q("SELECT 1 FROM settlements WHERE id=?", (s["id"],))
        row = {f: s.get(f) for f in SETTLEMENT_FIELDS}
        row["states"] = json.dumps(row["states"] or [])
        row["fetched_at"] = time.time()
        cols = ",".join(row)
        self.x(f"INSERT INTO settlements({cols}) VALUES({','.join('?' * len(row))}) "
               f"ON CONFLICT(id) DO UPDATE SET {','.join(f'{c}=excluded.{c}' for c in row if c != 'id')}",
               tuple(row.values()))
        return new

    def settlement(self, sid):
        rows = self.q("SELECT * FROM settlements WHERE id=?", (sid,))
        return _decode(rows[0]) if rows else None

    def settlements(self, open_only=True, today=None):
        today = today or time.strftime("%Y-%m-%d")
        sql = "SELECT * FROM settlements"
        args = ()
        if open_only:
            sql += " WHERE deadline IS NULL OR deadline >= ?"
            args = (today,)
        return [_decode(r) for r in self.q(sql + " ORDER BY deadline IS NULL, deadline", args)]


def _decode(row):
    row["states"] = json.loads(row.get("states") or "[]")
    return row
