import argparse
import logging
from typing import Optional

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, model_validator

from . import cache, musicbrainz, openai_fallback
from .config import HOST, PORT, REPLACEMENT_CHAR

# Which backends to use: "all", "openai", or "musicbrainz"
BACKEND: str = "all"

app = FastAPI(title="songfix", version="0.2.0", description="Correct corrupted song/artist names")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
log = logging.getLogger("songfix")


# --- Request / Response models ---


class FixRequest(BaseModel):
    """Accepts either new-style (artist/song) or legacy (name/type) fields."""
    artist: Optional[str] = None
    song: Optional[str] = None
    # Legacy fields
    name: Optional[str] = None
    type: Optional[str] = None

    @model_validator(mode="after")
    def _require_at_least_one(self):
        if not self.artist and not self.song and not self.name:
            raise ValueError("Provide at least one of: artist, song, or name")
        return self


class FieldResult(BaseModel):
    input: str
    corrected: str
    source: str
    confidence: float


class FixResponse(BaseModel):
    artist: Optional[FieldResult] = None
    song: Optional[FieldResult] = None


# Legacy response kept for backward-compatible GET endpoint
class LegacyFixResponse(BaseModel):
    input: str
    corrected: str
    source: str
    confidence: float


# --- Core resolution ---


async def _resolve_pair(artist: Optional[str], song: Optional[str]) -> FixResponse:
    """Resolve corrections for an artist/song pair."""

    # 1. Cache
    cached = cache.get_pair_cached(artist, song)
    if cached:
        log.info("pair cache hit for artist=%r song=%r", artist, song)
        resp_fields: dict = {}
        if artist is not None and "artist" in cached:
            resp_fields["artist"] = FieldResult(input=artist, **cached["artist"])
        if song is not None and "song" in cached:
            resp_fields["song"] = FieldResult(input=song, **cached["song"])
        if resp_fields:
            return FixResponse(**resp_fields)

    results: dict = {}

    # 2. MusicBrainz (per-field, using both for context)
    if BACKEND in ("all", "musicbrainz"):
        try:
            mb = await musicbrainz.lookup_pair(artist, song)
        except Exception:
            log.exception("MusicBrainz error for artist=%r song=%r", artist, song)
            mb = {}

        if mb:
            results.update(mb)
            log.info("musicbrainz results: %s", {k: v["corrected"] for k, v in mb.items()})

    # 3. OpenAI for any fields still unresolved
    artist_needs_fix = (
        artist is not None
        and "artist" not in results
        and REPLACEMENT_CHAR in artist
    )
    song_needs_fix = (
        song is not None
        and "song" not in results
        and REPLACEMENT_CHAR in song
    )

    if BACKEND in ("all", "openai") and (artist_needs_fix or song_needs_fix):
        # Pass both fields for context, even if only one needs fixing
        try:
            ai = await openai_fallback.correct(artist=artist, song=song)
        except Exception:
            log.exception("OpenAI error for artist=%r song=%r", artist, song)
            ai = None

        if ai:
            for field in ("artist", "song"):
                if field not in results and field in ai:
                    results[field] = ai[field]
                    log.info("openai %s: %r -> %r", field, locals().get(field), ai[field]["corrected"])

    # 4. Build response — include all provided fields
    resp_fields = {}
    if artist is not None:
        if "artist" in results:
            resp_fields["artist"] = FieldResult(input=artist, **results["artist"])
        else:
            resp_fields["artist"] = FieldResult(
                input=artist, corrected=artist, source="none", confidence=0.0
            )
    if song is not None:
        if "song" in results:
            resp_fields["song"] = FieldResult(input=song, **results["song"])
        else:
            resp_fields["song"] = FieldResult(
                input=song, corrected=song, source="none", confidence=0.0
            )

    # Cache results
    cacheable = {}
    for field in ("artist", "song"):
        if field in resp_fields:
            fr = resp_fields[field]
            cacheable[field] = {"corrected": fr.corrected, "source": fr.source, "confidence": fr.confidence}
    if cacheable:
        cache.set_pair_cached(artist, song, results=cacheable)

    return FixResponse(**resp_fields)


# --- Legacy single-field resolution (backward compat) ---


async def _resolve_legacy(name: str, type_: str) -> LegacyFixResponse:
    """Legacy single-field resolve — maps to pair-based resolution."""
    if type_ == "artist":
        resp = await _resolve_pair(artist=name, song=None)
        fr = resp.artist
    elif type_ in ("song", "recording"):
        resp = await _resolve_pair(artist=None, song=name)
        fr = resp.song
    else:
        # auto: try as artist first via pair, fall back to song
        resp = await _resolve_pair(artist=name, song=None)
        fr = resp.artist
        if fr and fr.source == "none":
            resp = await _resolve_pair(artist=None, song=name)
            fr = resp.song

    if fr:
        return LegacyFixResponse(input=fr.input, corrected=fr.corrected, source=fr.source, confidence=fr.confidence)
    return LegacyFixResponse(input=name, corrected=name, source="none", confidence=0.0)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/fix", response_model=LegacyFixResponse)
async def fix_get(
    name: str = Query(..., description="Corrupted song or artist name"),
    type: Optional[str] = Query("auto", description="artist, song, or auto"),
):
    """Legacy GET endpoint — single name + type."""
    return await _resolve_legacy(name, type)


@app.post("/fix", response_model=FixResponse)
async def fix_post(req: FixRequest):
    # Legacy POST: if only name/type provided, map to old behavior
    if req.name and not req.artist and not req.song:
        legacy = await _resolve_legacy(req.name, req.type or "auto")
        # Wrap in new response shape
        if (req.type or "auto") == "artist":
            return FixResponse(artist=FieldResult(**legacy.model_dump()))
        elif (req.type or "auto") in ("song", "recording"):
            return FixResponse(song=FieldResult(**legacy.model_dump()))
        else:
            return FixResponse(song=FieldResult(**legacy.model_dump()))

    return await _resolve_pair(req.artist, req.song)


def main():
    global BACKEND
    parser = argparse.ArgumentParser(description="songfix server")
    parser.add_argument(
        "--backend",
        choices=["all", "openai", "musicbrainz"],
        default="all",
        help="Which lookup backend(s) to use (default: all)",
    )
    args = parser.parse_args()
    BACKEND = args.backend
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log.info("Starting songfix with backend=%s", BACKEND)
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
