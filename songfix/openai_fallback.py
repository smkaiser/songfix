import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from .config import OPENAI_API_KEY, OPENAI_MODEL, REPLACEMENT_CHAR

log = logging.getLogger("songfix")

_SYSTEM = (
    "You are a music expert. The user will give you a song title and/or artist name. "
    "One or both may have corrupted characters (the Unicode replacement character \ufffd). "
    "Each corrupted character should be replaced by a SINGLE accented or special character "
    "that fits the context or language of the rest of the input.\n\n"
    "Rules:\n"
    "- Only fix fields that contain the \ufffd character.\n"
    "- Leave fields without \ufffd EXACTLY as provided — do not change spelling, "
    "punctuation, or capitalization.\n"
    "- Reply with ONLY a JSON object: {\"artist\": \"...\", \"song\": \"...\"}\n"
    "- Omit a key if the user did not provide that field.\n"
    "- No explanation, no markdown, no extra text."
)


async def correct(
    artist: Optional[str] = None,
    song: Optional[str] = None,
) -> Optional[dict]:
    """Use OpenAI to correct corrupted artist/song names.

    Pass both fields when available for better context.
    Returns dict with 'artist' and/or 'song' sub-dicts, or None.
    """
    if not OPENAI_API_KEY:
        return None

    artist_corrupted = artist is not None and REPLACEMENT_CHAR in artist
    song_corrupted = song is not None and REPLACEMENT_CHAR in song

    if not artist_corrupted and not song_corrupted:
        result = {}
        if artist is not None:
            result["artist"] = {"corrected": artist, "source": "openai", "confidence": 1.0}
        if song is not None:
            result["song"] = {"corrected": song, "source": "openai", "confidence": 1.0}
        return result or None

    parts = []
    if artist is not None:
        parts.append(f"Artist: {artist}")
    if song is not None:
        parts.append(f"Song: {song}")
    prompt = "\n".join(parts)

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    resp = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        max_completion_tokens=200,
    )
    raw = resp.choices[0].message.content.strip() if resp.choices else None
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("OpenAI returned non-JSON response: %r", raw)
        return None

    result = {}
    if artist is not None and "artist" in data:
        corrected_artist = data["artist"]
        # Guard: if artist wasn't corrupted, keep original
        if not artist_corrupted:
            corrected_artist = artist
        result["artist"] = {"corrected": corrected_artist, "source": "openai", "confidence": 0.8}
    if song is not None and "song" in data:
        corrected_song = data["song"]
        if not song_corrupted:
            corrected_song = song
        result["song"] = {"corrected": corrected_song, "source": "openai", "confidence": 0.8}

    return result or None
