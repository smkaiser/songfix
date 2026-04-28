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

_CREATE_PAIR_TABLE = """
CREATE TABLE IF NOT EXISTS pair_corrections (
    input_artist TEXT NOT NULL DEFAULT '',
    input_song   TEXT NOT NULL DEFAULT '',
    field        TEXT NOT NULL,
    corrected    TEXT NOT NULL,
    source       TEXT NOT NULL,
    confidence   REAL NOT NULL,
    PRIMARY KEY (input_artist, input_song, field)
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_CREATE_TABLE)
    conn.execute(_CREATE_PAIR_TABLE)
    return conn


def get_cached(name: str, type_: str) -> Optional[dict]:
    """Return cached correction or None (legacy single-field)."""
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


def get_pair_cached(
    artist: Optional[str] = None, song: Optional[str] = None
) -> Optional[dict]:
    """Return cached pair correction or None.

    Returns dict like ``{"artist": {"corrected": ..., "source": ..., "confidence": ...}, ...}``
    """
    conn = _connect()
    rows = conn.execute(
        "SELECT field, corrected, source, confidence FROM pair_corrections "
        "WHERE input_artist = ? AND input_song = ?",
        (artist or "", song or ""),
    ).fetchall()
    conn.close()
    if not rows:
        return None
    result = {}
    for field, corrected, source, confidence in rows:
        result[field] = {"corrected": corrected, "source": source, "confidence": confidence}
    return result


def set_pair_cached(
    artist: Optional[str] = None,
    song: Optional[str] = None,
    *,
    results: dict,
) -> None:
    """Cache per-field results for an artist/song pair.

    ``results`` is ``{"artist": {"corrected": ..., "source": ..., "confidence": ...}, ...}``
    """
    conn = _connect()
    for field, data in results.items():
        conn.execute(
            "INSERT OR REPLACE INTO pair_corrections "
            "(input_artist, input_song, field, corrected, source, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (artist or "", song or "", field, data["corrected"], data["source"], data["confidence"]),
        )
    conn.commit()
    conn.close()
