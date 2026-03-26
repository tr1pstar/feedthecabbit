import os

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
_raw_db_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://cabbit:cabbit@localhost:5432/cabbit")
# Railway/Render may give postgres:// or postgresql:// — normalize to postgresql+asyncpg://
if _raw_db_url.startswith("postgres://"):
    DATABASE_URL = _raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw_db_url.startswith("postgresql://"):
    DATABASE_URL = _raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = _raw_db_url
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
CRYPTOPAY_TOKEN: str = os.getenv("CRYPTOPAY_TOKEN", "")
CRYPTOPAY_TESTNET: bool = os.getenv("CRYPTOPAY_TESTNET", "true").lower() == "true"
REQUIRED_CHANNEL: str = os.getenv("REQUIRED_CHANNEL", "")
NOTIFY_BOT_TOKEN: str = os.getenv("NOTIFY_BOT_TOKEN", "")
