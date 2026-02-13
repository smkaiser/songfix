# songfix

A small local HTTP server that corrects corrupted song and artist names — where characters like `ö`, `á`, `ü` have been replaced with `�` (U+FFFD).

**Examples:**
- `Bj�rk` → `Björk`
- `Tri�ngulo de amor bizarro` → `Triángulo de amor bizarro`
- `Mot�rhead` → `Motörhead`

## How it works

1. **Cache** — checks a local SQLite database for previously corrected names
2. **MusicBrainz** — free fuzzy search against a massive music database (no API key needed)
3. **OpenAI fallback** — if MusicBrainz can't match, uses `gpt-4o-mini` for a best guess (requires API key)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Start the server:

```bash
source .venv/bin/activate
python -m songfix.server
```

The server runs at `http://127.0.0.1:8042` by default.

### Endpoints

**GET /fix**

```bash
curl "http://127.0.0.1:8042/fix?name=Bj%EF%BF%BDrk&type=artist"
```

**POST /fix**

```bash
curl -X POST http://127.0.0.1:8042/fix \
  -H "Content-Type: application/json" \
  -d '{"name": "Bj\ufffd rk", "type": "artist"}'
```

**Response:**

```json
{
  "input": "Bj�rk",
  "corrected": "Björk",
  "source": "musicbrainz",
  "confidence": 0.95
}
```

**GET /health**

```bash
curl http://127.0.0.1:8042/health
```

### Parameters

| Parameter | Values | Default | Description |
|-----------|--------|---------|-------------|
| `name` | any string | (required) | The corrupted name to fix |
| `type` | `artist`, `song`, `auto` | `auto` | What kind of name it is |

### Interactive docs

FastAPI auto-generates OpenAPI docs at [http://127.0.0.1:8042/docs](http://127.0.0.1:8042/docs).

## Configuration

All settings are via environment variables:

| Variable               | Default            | Description                          |
| ---------------------- | ------------------ | ------------------------------------ |
| `OPENAI_API_KEY`       | *(none)*           | Required for OpenAI fallback         |
| `SONGFIX_OPENAI_MODEL` | `gpt-4o-mini`      | OpenAI model to use                  |
| `SONGFIX_HOST`         | `127.0.0.1`        | Server bind address (use 0.0.0.0 to allow external access) |
| `SONGFIX_PORT`         | `8042`             | Server port                          |
| `SONGFIX_DB`           | `songfix_cache.db` | SQLite cache file path               |
| `SONGFIX_MB_THRESHOLD` | `0.6`              | MusicBrainz minimum confidence (0–1) |
