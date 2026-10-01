"""SQLite persistence layer for FoodRescue.

All functions take an explicit connection; callers get one via ``connect()``.
Pass ``path=...`` (or set ``FOODRESCUE_DB``) to point at a different database,
which is what the test-suite does for isolation.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

DEFAULT_DB = (
    Path.home() / "workspace" / "github-vault" / "foodrescue" / "data" / "foodrescue.db"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    donor       TEXT NOT NULL,
    meals       INTEGER NOT NULL CHECK (meals > 0),
    expires_at  INTEGER NOT NULL,          -- unix timestamp
    x           REAL NOT NULL,
    y           REAL NOT NULL,
    tags        TEXT NOT NULL DEFAULT '[]', -- JSON array of dietary tags
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS shelters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    x           REAL NOT NULL,
    y           REAL NOT NULL,
    capacity    INTEGER NOT NULL CHECK (capacity > 0), -- meals it can take per run
    needs       TEXT NOT NULL DEFAULT '[]',            -- JSON array of dietary needs
    hours       TEXT NOT NULL DEFAULT '9-17'            -- operating hours "open-close"
);

CREATE TABLE IF NOT EXISTS matches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id  INTEGER NOT NULL REFERENCES listings(id),
    shelter_id  INTEGER NOT NULL REFERENCES shelters(id),
    score       REAL NOT NULL,
    breakdown   TEXT NOT NULL,   -- JSON: component scores + weights
    status      TEXT NOT NULL DEFAULT 'matched',
    created_at  INTEGER NOT NULL
);
"""

STATUSES = ("open", "matched", "claimed", "picked_up", "completed", "expired")


def resolve_db(path: str | Path | None = None) -> Path:
    if path:
        return Path(path)
    env = os.environ.get("FOODRESCUE_DB")
    if env:
        return Path(env)
    return DEFAULT_DB


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    db_path = resolve_db(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("tags", "needs", "breakdown"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except json.JSONDecodeError:
                pass
    return d


# ---------------------------------------------------------------- listings ---
def add_listing(
    conn: sqlite3.Connection,
    *,
    title: str,
    donor: str,
    meals: int,
    expires_at: int,
    x: float,
    y: float,
    tags: list[str] | None = None,
    status: str = "open",
    now: float | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO listings (title, donor, meals, expires_at, x, y, tags, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            title,
            donor,
            meals,
            int(expires_at),
            x,
            y,
            json.dumps(tags or []),
            status,
            int(now if now is not None else time.time()),
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_listing(conn: sqlite3.Connection, listing_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_listings(
    conn: sqlite3.Connection, status: str | None = None
) -> list[dict]:
    if status:
        rows = conn.execute(
            "SELECT * FROM listings WHERE status = ? ORDER BY expires_at", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM listings ORDER BY expires_at").fetchall()
    return [_row_to_dict(r) for r in rows]


def set_listing_status(conn: sqlite3.Connection, listing_id: int, status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    conn.execute("UPDATE listings SET status = ? WHERE id = ?", (status, listing_id))
    conn.commit()


# ---------------------------------------------------------------- shelters ---
def add_shelter(
    conn: sqlite3.Connection,
    *,
    name: str,
    x: float,
    y: float,
    capacity: int,
    needs: list[str] | None = None,
    hours: str = "9-17",
) -> int:
    cur = conn.execute(
        "INSERT INTO shelters (name, x, y, capacity, needs, hours) VALUES (?, ?, ?, ?, ?, ?)",
        (name, x, y, capacity, json.dumps(needs or []), hours),
    )
    conn.commit()
    return cur.lastrowid


def list_shelters(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM shelters ORDER BY id").fetchall()
    return [_row_to_dict(r) for r in rows]


# ----------------------------------------------------------------- matches ---
def record_match(
    conn: sqlite3.Connection,
    *,
    listing_id: int,
    shelter_id: int,
    score: float,
    breakdown: dict,
    now: float | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO matches (listing_id, shelter_id, score, breakdown, status, created_at)"
        " VALUES (?, ?, ?, ?, 'matched', ?)",
        (
            listing_id,
            shelter_id,
            score,
            json.dumps(breakdown),
            int(now if now is not None else time.time()),
        ),
    )
    conn.commit()
    return cur.lastrowid


def list_matches(
    conn: sqlite3.Connection, status: str | None = None
) -> list[dict]:
    query = (
        "SELECT m.*, l.title AS listing_title, l.meals AS meals,"
        " s.name AS shelter_name"
        " FROM matches m"
        " JOIN listings l ON l.id = m.listing_id"
        " JOIN shelters s ON s.id = m.shelter_id"
    )
    if status:
        query += " WHERE m.status = ?"
        rows = conn.execute(query + " ORDER BY m.score DESC", (status,)).fetchall()
    else:
        rows = conn.execute(query + " ORDER BY m.score DESC").fetchall()
    return [_row_to_dict(r) for r in rows]


def set_match_status(conn: sqlite3.Connection, match_id: int, status: str) -> None:
    conn.execute("UPDATE matches SET status = ? WHERE id = ?", (status, match_id))
    conn.commit()
