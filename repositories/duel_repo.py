from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Duel

async def get(session: AsyncSession, challenger_id: int) -> Duel | None:
    return await session.get(Duel, challenger_id)

async def create(session: AsyncSession, challenger_id: int, target_id: int, stake: int) -> Duel:
    duel = Duel(
        challenger_id=challenger_id, target_id=target_id, stake=stake,
        round=1, scores={str(challenger_id): 0, str(target_id): 0},
        moves={}, status="pending",
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
