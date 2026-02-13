import os


OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.environ.get("SONGFIX_OPENAI_MODEL", "gpt-4o-mini")
HOST: str = os.environ.get("SONGFIX_HOST", "127.0.0.1")
PORT: int = int(os.environ.get("SONGFIX_PORT", "8042"))
DB_PATH: str = os.environ.get("SONGFIX_DB", "songfix_cache.db")
MB_USER_AGENT: str = "songfix/0.1.0 (https://github.com/songfix)"
MB_CONFIDENCE_THRESHOLD: float = float(os.environ.get("SONGFIX_MB_THRESHOLD", "0.6"))

# Unicode replacement character – the corrupted marker we look for
REPLACEMENT_CHAR = "\ufffd"
