import sqlite3
from typing import Optional

from .config import DB_PATH

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS corrections (
    input_name TEXT NOT NULL,
    type       TEXT NOT NULL,
    corrected  TEXT NOT NULL,
    source     TEXT NOT NULL,
    confidence REAL NOT NULL,
    PRIMARY KEY (input_name, type)
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_CREATE_TABLE)
    return conn


def get_cached(name: str, type_: str) -> Optional[dict]:
    """Return cached correction or None."""
    conn = _connect()
    row = conn.execute(
        "SELECT corrected, source, confidence FROM corrections WHERE input_name = ? AND type = ?",
        (name, type_),
    ).fetchone()
    conn.close()
    if row:
        return {"corrected": row[0], "source": row[1], "confidence": row[2]}
    return None


def set_cached(name: str, type_: str, corrected: str, source: str, confidence: float) -> None:
    conn = _connect()
    conn.execute(
        "INSERT OR REPLACE INTO corrections (input_name, type, corrected, source, confidence) VALUES (?, ?, ?, ?, ?)",
        (name, type_, corrected, source, confidence),
    )
    conn.commit()
    conn.close()
