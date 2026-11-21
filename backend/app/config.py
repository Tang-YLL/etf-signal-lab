from pathlib import Path
import os

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data" if Path("/app/data").exists() else "./data"))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'etf.db'}")
COOLDOWN = int(os.getenv("MARKET_CHECK_COOLDOWN_SECONDS", "600"))
DATA_SOURCE = os.getenv("MARKET_DATA_PROVIDER", "akshare")
REQUEST_TIMEOUT = float(os.getenv("MARKET_REQUEST_TIMEOUT_SECONDS", "15"))
