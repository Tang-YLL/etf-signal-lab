from pathlib import Path
import os
import secrets

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data" if Path("/app/data").exists() else "./data"))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'etf.db'}")
COOLDOWN = int(os.getenv("MARKET_CHECK_COOLDOWN_SECONDS", "600"))
DATA_SOURCE = os.getenv("MARKET_DATA_PROVIDER", "akshare")
REQUEST_TIMEOUT = float(os.getenv("MARKET_REQUEST_TIMEOUT_SECONDS", "15"))
COOKIE_HTTPS = os.getenv("COOKIE_HTTPS", "false").lower() == "true"

def session_secret() -> str:
    """Stable random signing key stored in server volume, never in repo."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / ".session-secret"
    if not path.exists():
        try:
            with path.open("x") as file:
                file.write(secrets.token_urlsafe(48))
            path.chmod(0o600)
        except FileExistsError:
            pass
    return path.read_text().strip()
