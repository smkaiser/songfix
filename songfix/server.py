import logging
from typing import Optional

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import cache, musicbrainz, openai_fallback
from .config import HOST, PORT

app = FastAPI(title="songfix", version="0.1.0", description="Correct corrupted song/artist names")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
log = logging.getLogger("songfix")


class FixRequest(BaseModel):
    name: str
    type: str = "auto"


class FixResponse(BaseModel):
    input: str
    corrected: str
    source: str
    confidence: float


async def _resolve(name: str, type_: str) -> FixResponse:
    # 1. Cache
    cached = cache.get_cached(name, type_)
    if cached:
        log.info("cache hit for %r", name)
        return FixResponse(input=name, **cached)

    # 2. MusicBrainz
    try:
        mb = await musicbrainz.lookup(name, type_)
    except Exception:
        log.exception("MusicBrainz error for %r", name)
        mb = None

    if mb:
        log.info("musicbrainz match for %r -> %r", name, mb["corrected"])
        cache.set_cached(name, type_, **mb)
        return FixResponse(input=name, **mb)

    # 3. OpenAI fallback
    try:
        ai = await openai_fallback.correct(name, type_)
    except Exception:
        log.exception("OpenAI error for %r", name)
        ai = None

    if ai:
        log.info("openai match for %r -> %r", name, ai["corrected"])
        cache.set_cached(name, type_, **ai)
        return FixResponse(input=name, **ai)

    # 4. Nothing worked — return input unchanged
    return FixResponse(input=name, corrected=name, source="none", confidence=0.0)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/fix", response_model=FixResponse)
async def fix_get(
    name: str = Query(..., description="Corrupted song or artist name"),
    type: Optional[str] = Query("auto", description="artist, song, or auto"),
):
    return await _resolve(name, type)


@app.post("/fix", response_model=FixResponse)
async def fix_post(req: FixRequest):
    return await _resolve(req.name, req.type)


def main():
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
