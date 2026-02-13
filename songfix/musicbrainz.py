import asyncio
import logging
import re
import ssl
import time
from typing import Optional

import httpx

from .config import MB_CONFIDENCE_THRESHOLD, MB_USER_AGENT, REPLACEMENT_CHAR

log = logging.getLogger("songfix")

# Explicit SSL context needed for Python 3.14 + httpx inside uvicorn's event loop
_ssl_ctx = ssl.create_default_context()

_BASE = "https://musicbrainz.org/ws/2"
_last_request: float = 0.0
_lock = asyncio.Lock()
_MAX_RETRIES = 3

# Shared persistent client (created lazily)
_client: Optional[httpx.AsyncClient] = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=10,
            verify=_ssl_ctx,
            headers={"User-Agent": MB_USER_AGENT},
            http2=False,
        )
    return _client


# Lucene special chars to escape (keep _ as wildcard for our replacement chars)
_LUCENE_ESCAPE = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\\/])')


def _build_query(name: str) -> str:
    """Replace � with Lucene single-char wildcard `_` and escape other special chars.

    Words that contained a replacement character get a trailing ``~`` so
    MusicBrainz applies fuzzy matching to them.
    """
    words = name.split()
    out: list[str] = []
    for word in words:
        has_replacement = REPLACEMENT_CHAR in word
        word = word.replace(REPLACEMENT_CHAR, "_")
        word = _LUCENE_ESCAPE.sub(r"\\\1", word)
        if has_replacement:
            word += "~"
        out.append(word)
    return " ".join(out)


async def _rate_limit() -> None:
    """Enforce MusicBrainz 1-request-per-second policy."""
    global _last_request
    async with _lock:
        now = time.monotonic()
        wait = max(0.0, 1.0 - (now - _last_request))
        if wait:
            await asyncio.sleep(wait)
        _last_request = time.monotonic()


async def _search(entity: str, query: str, limit: int = 5) -> list[dict]:
    for attempt in range(_MAX_RETRIES):
        await _rate_limit()
        try:
            client = await _get_client()
            resp = await client.get(
                f"{_BASE}/{entity}",
                params={"query": query, "fmt": "json", "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get(f"{entity}s", [])
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            global _client
            # Force a fresh connection on next attempt
            if _client and not _client.is_closed:
                await _client.aclose()
            _client = None
            if attempt == _MAX_RETRIES - 1:
                raise
            log.warning("MusicBrainz connect error (attempt %d/%d): %s", attempt + 1, _MAX_RETRIES, exc)
            await asyncio.sleep(1.0)
    return []


async def search_artist(name: str) -> Optional[dict]:
    query = _build_query(name)
    if not query.strip():
        return None
    results = await _search("artist", query)
    for item in results:
        score = item.get("score", 0) / 100.0
        if score >= MB_CONFIDENCE_THRESHOLD:
            return {"corrected": item["name"], "source": "musicbrainz", "confidence": round(score, 3)}
    return None


async def search_recording(name: str) -> Optional[dict]:
    query = _build_query(name)
    if not query.strip():
        return None
    results = await _search("recording", query)
    for item in results:
        score = item.get("score", 0) / 100.0
        if score >= MB_CONFIDENCE_THRESHOLD:
            return {"corrected": item["title"], "source": "musicbrainz", "confidence": round(score, 3)}
    return None


async def lookup(name: str, type_: str = "auto") -> Optional[dict]:
    """Search MusicBrainz for the corrected name. Returns dict or None."""
    if type_ == "artist":
        return await search_artist(name)
    if type_ == "song":
        return await search_recording(name)
    # auto: try artist first, then recording
    result = await search_artist(name)
    if result:
        return result
    return await search_recording(name)
