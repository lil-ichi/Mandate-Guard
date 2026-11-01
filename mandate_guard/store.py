"""SQLite store: mandates, spend counters, decisions.

Replaces the old JSON/JSONL files. Spend counters roll over automatically:
a new calendar day zeroes the daily total, a new month zeroes the monthly
total — no manual reset needed. Decisions are also mirrored to decisions.jsonl
as a human-readable audit export.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import date

BASE = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.environ.get("MANDATE_DB", os.path.join(BASE, "mandate_guard.db"))
JSONL_PATH = os.environ.get(
    "DECISION_LOG", os.path.join(BASE, "decisions.jsonl")
)
SEED_PATH = os.path.join(BASE, "mandates.json")


@dataclass
class Mandate:
    agent_id: str
    daily_cap: float
    monthly_cap: float
    currency: str = "USD"
    vendor_allowlist: list = field(default_factory=list)
    human_approval_above: float = 500.0
    spent_today: float = 0.0
    spent_month: float = 0.0


_SCHEMA = """
CREATE TABLE IF NOT EXISTS mandates (
    agent_id TEXT PRIMARY KEY,
    daily_cap REAL NOT NULL,
    monthly_cap REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    vendor_allowlist TEXT NOT NULL DEFAULT '[]',
    human_approval_above REAL NOT NULL DEFAULT 500.0
);
CREATE TABLE IF NOT EXISTS spend (
    agent_id TEXT PRIMARY KEY,
    day TEXT NOT NULL,
    month TEXT NOT NULL,
    spent_day REAL NOT NULL DEFAULT 0,
    spent_month REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    ts INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    vendor TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    idempotency_key TEXT UNIQUE,
    verdict TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_agent_ts
    ON decisions(agent_id, ts DESC);
"""


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return con


def seed() -> None:
    """Load mandates.json into the DB on first run (human-editable config)."""
    con = _conn()
    try:
        if con.execute("SELECT COUNT(*) c FROM mandates").fetchone()["c"]:
            return
        if not os.path.exists(SEED_PATH):
            return
        with open(SEED_PATH) as f:
            raw = json.load(f)
        for agent_id, m in raw.items():
            con.execute(
                "INSERT INTO mandates VALUES (?,?,?,?,?,?)",
                (agent_id, m["daily_cap"], m["monthly_cap"],
                 m.get("currency", "USD"),
                 json.dumps(m.get("vendor_allowlist", [])),
                 m.get("human_approval_above", 500.0)),
            )
        con.commit()
    finally:
        con.close()


def get_mandate(agent_id: str) -> Mandate | None:
    seed()
    con = _conn()
    try:
        row = con.execute(
            "SELECT * FROM mandates WHERE agent_id=?", (agent_id,)
        ).fetchone()
        if not row:
            return None
        day_total, month_total = get_spend(agent_id, con)
        return Mandate(
            agent_id=row["agent_id"],
            daily_cap=row["daily_cap"],
            monthly_cap=row["monthly_cap"],
            currency=row["currency"],
            vendor_allowlist=json.loads(row["vendor_allowlist"]),
            human_approval_above=row["human_approval_above"],
            spent_today=day_total,
            spent_month=month_total,
        )
    finally:
        con.close()


def upsert_mandate(m: Mandate) -> None:
    seed()
    con = _conn()
    try:
        con.execute(
            """INSERT INTO mandates
               (agent_id, daily_cap, monthly_cap, currency,
                vendor_allowlist, human_approval_above)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(agent_id) DO UPDATE SET
                 daily_cap=excluded.daily_cap,
                 monthly_cap=excluded.monthly_cap,
                 currency=excluded.currency,
                 vendor_allowlist=excluded.vendor_allowlist,
                 human_approval_above=excluded.human_approval_above""",
            (m.agent_id, m.daily_cap, m.monthly_cap, m.currency,
             json.dumps(m.vendor_allowlist), m.human_approval_above),
        )
        con.commit()
    finally:
        con.close()


def get_spend(agent_id: str, con: sqlite3.Connection | None = None
              ) -> tuple[float, float]:
    """(spent_today, spent_month) with automatic day/month rollover."""
    today = date.today().isoformat()
    month = today[:7]
    own = con is None
    con = con or _conn()
    try:
        row = con.execute(
            "SELECT day, month, spent_day, spent_month FROM spend"
            " WHERE agent_id=?", (agent_id,)
        ).fetchone()
        if not row:
            return 0.0, 0.0
        spent_day = row["spent_day"] if row["day"] == today else 0.0
        spent_month = row["spent_month"] if row["month"] == month else 0.0
        return spent_day, spent_month
    finally:
        if own:
            con.close()


def record_spend(agent_id: str, amount: float) -> None:
    today = date.today().isoformat()
    month = today[:7]
    con = _conn()
    try:
        day_total, month_total = get_spend(agent_id, con)
        con.execute(
            """INSERT INTO spend (agent_id, day, month, spent_day, spent_month)
               VALUES (?,?,?,?,?)
               ON CONFLICT(agent_id) DO UPDATE SET
                 day=excluded.day, month=excluded.month,
                 spent_day=excluded.spent_day,
                 spent_month=excluded.spent_month""",
            (agent_id, today, month, day_total + amount,
             month_total + amount),
        )
        con.commit()
    finally:
        con.close()


def append_decision(record: dict) -> None:
    con = _conn()
    try:
        con.execute(
            """INSERT INTO decisions
               (id, ts, agent_id, amount, currency, vendor, purpose,
                decision, reason, idempotency_key, verdict)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (record["decision_id"], record["ts"], record["agent_id"],
             record["amount"], record["currency"], record["vendor"],
             record.get("purpose", ""), record["decision"], record["reason"],
             record.get("idempotency_key"), record["verdict"]),
        )
        con.commit()
    finally:
        con.close()
    # Human-readable audit export alongside the DB.
    with open(JSONL_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def _row_to_record(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["decision_id"] = d.pop("id")
    return d


def recent_decisions(limit: int = 10) -> list[dict]:
    con = _conn()
    try:
        rows = con.execute(
            "SELECT * FROM decisions ORDER BY ts DESC, rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_record(r) for r in rows]
    finally:
        con.close()


def find_by_idempotency(key: str) -> dict | None:
    con = _conn()
    try:
        row = con.execute(
            "SELECT * FROM decisions WHERE idempotency_key=? ORDER BY ts DESC"
            " LIMIT 1", (key,),
        ).fetchone()
        return _row_to_record(row) if row else None
    finally:
        con.close()


def reset() -> None:
    """Clear spend + decisions (demos/evals). Mandates survive."""
    seed()
    con = _conn()
    try:
        con.execute("DELETE FROM spend")
        con.execute("DELETE FROM decisions")
        con.commit()
    finally:
        con.close()
    if os.path.exists(JSONL_PATH):
        os.remove(JSONL_PATH)


def mandates_as_dict() -> dict:
    """For debugging / the study pack."""
    seed()
    con = _conn()
    try:
        return {r["agent_id"]: asdict(get_mandate(r["agent_id"]))
                for r in con.execute("SELECT agent_id FROM mandates")}
    finally:
        con.close()


if __name__ == "__main__":
    seed()
    print("db:", DB_PATH)
    print("mandates:", list(mandates_as_dict()))
