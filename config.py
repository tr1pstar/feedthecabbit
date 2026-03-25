import os

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://cabbit:cabbit@localhost:5432/cabbit")
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
