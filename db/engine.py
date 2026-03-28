from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from contextlib import asynccontextmanager
from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    from db.models import Base
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migrate: add uid column if missing
        cols = await conn.run_sync(
            lambda sync_conn: [
                r[0] for r in sync_conn.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name='cabbits'")
                )
            ]
        )
        # Ensure uid is BIGINT (might have been created as INTEGER)
        if "uid" in cols:
            await conn.execute(text("ALTER TABLE cabbits ALTER COLUMN uid TYPE BIGINT"))
        if "uid" not in cols:
            await conn.execute(text("CREATE SEQUENCE IF NOT EXISTS cabbit_uid_seq"))
            await conn.execute(text(
                "ALTER TABLE cabbits ADD COLUMN uid INTEGER UNIQUE DEFAULT nextval('cabbit_uid_seq')"
            ))
            await conn.execute(text(
                "UPDATE cabbits SET uid = nextval('cabbit_uid_seq') WHERE uid IS NULL"
            ))
            await conn.execute(text("ALTER TABLE cabbits ALTER COLUMN uid SET NOT NULL"))
        # Migrate: add move columns to duels
        duel_cols_pre = await conn.run_sync(
            lambda sc: [r[0] for r in sc.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='duels'"))]
        )
        if "challenger_move" not in duel_cols_pre:
            await conn.execute(text("ALTER TABLE duels ADD COLUMN challenger_move VARCHAR(16)"))
            await conn.execute(text("ALTER TABLE duels ADD COLUMN target_move VARCHAR(16)"))
        if "duel_type" not in duel_cols_pre:
            await conn.execute(text("ALTER TABLE duels ADD COLUMN duel_type VARCHAR(8) DEFAULT 'rps'"))
            await conn.execute(text("ALTER TABLE duels ADD COLUMN chat_id BIGINT"))

        # Migrate: add round_started_at to duels
        duel_cols = await conn.run_sync(
            lambda sync_conn: [
                r[0] for r in sync_conn.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name='duels'")
                )
            ]
        )
        if "round_started_at" not in duel_cols:
            await conn.execute(text("ALTER TABLE duels ADD COLUMN round_started_at INTEGER DEFAULT 0"))

        if "referred_by" not in cols:
            await conn.execute(text("ALTER TABLE cabbits ADD COLUMN referred_by BIGINT"))
        if "referral_rewarded" not in cols:
            await conn.execute(text("ALTER TABLE cabbits ADD COLUMN referral_rewarded BOOLEAN DEFAULT false"))
        # Re-read cols to check for autocollect_until
        cols2 = await conn.run_sync(
            lambda sync_conn: [
                r[0] for r in sync_conn.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name='cabbits'")
                )
            ]
        )
        if "knife_until" not in cols2:
            await conn.execute(text("ALTER TABLE cabbits ADD COLUMN knife_until INTEGER DEFAULT 0"))
        if "autocollect_until" not in cols2:
            await conn.execute(text("ALTER TABLE cabbits ADD COLUMN autocollect_until INTEGER DEFAULT 0"))

@asynccontextmanager
async def get_session():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
