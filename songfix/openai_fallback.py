from typing import Optional

from openai import AsyncOpenAI

from .config import OPENAI_API_KEY, OPENAI_MODEL, REPLACEMENT_CHAR

_SYSTEM = (
    "You are a music expert. The user will give you a song title or artist name "
    "that has one or more corrupted characters (the Unicode replacement character \ufffd). "
    "Reply with ONLY the corrected name — no explanation, no quotes, no punctuation "
    "other than what belongs in the name. The corrupted character should be replaced by a SINGLE accented or sspecial character that fits the context or language of the rest of the input."
)


async def correct(name: str, type_: str = "auto") -> Optional[dict]:
    """Use OpenAI to guess the correct name. Returns dict or None."""
    if not OPENAI_API_KEY:
        return None
    if REPLACEMENT_CHAR not in name:
        return {"corrected": name, "source": "openai", "confidence": 1.0}

    kind = {"artist": "artist name", "song": "song title"}.get(type_, "song title or artist name")
    prompt = f"The following {kind} has corrupted characters ({REPLACEMENT_CHAR}). What is the correct name?\n\n{name}"

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    resp = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        max_completion_tokens=120,
    )
    corrected = resp.choices[0].message.content.strip() if resp.choices else None
    if corrected:
        return {"corrected": corrected, "source": "openai", "confidence": 0.8}
    return None
