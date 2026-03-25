import time
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Duel


async def get(session: AsyncSession, challenger_id: int) -> Duel | None:
    return await session.get(Duel, challenger_id)


async def create(session: AsyncSession, challenger_id: int, target_id: int, stake: int) -> Duel:
    duel = Duel(
        challenger_id=challenger_id, target_id=target_id, stake=stake,
        round=1, scores={str(challenger_id): 0, str(target_id): 0},
        moves={}, status="pending", created_at=int(time.time()),
    )
    session.add(duel)
    await session.flush()
    return duel


async def save(session: AsyncSession, duel: Duel) -> None:
    session.add(duel)
    await session.flush()


async def delete(session: AsyncSession, challenger_id: int) -> Duel | None:
    duel = await get(session, challenger_id)
    if duel:
        await session.delete(duel)
        await session.flush()
    return duel


async def find_by_user(session: AsyncSession, user_id: int) -> Duel | None:
    """Find any active/pending duel where user is challenger or target."""
    r = await session.execute(
        select(Duel).where(
            Duel.status.in_(["pending", "active"]),
            or_(Duel.challenger_id == user_id, Duel.target_id == user_id),
        ).limit(1)
    )
    return r.scalar_one_or_none()


async def get_expired_pending(session: AsyncSession, threshold: int) -> list[Duel]:
    """Get pending duels created before threshold timestamp."""
    r = await session.execute(
        select(Duel).where(
            Duel.status == "pending",
            Duel.created_at < threshold,
            Duel.created_at > 0,
        )
    )
    return list(r.scalars().all())


async def get_all(session: AsyncSession) -> list[Duel]:
    r = await session.execute(select(Duel))
    return list(r.scalars().all())
