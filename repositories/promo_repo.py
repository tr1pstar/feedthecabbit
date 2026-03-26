from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Promo

async def get(session: AsyncSession, code: str) -> Promo | None:
    return await session.get(Promo, code)

async def create(session: AsyncSession, code: str, promo_type: str,
                 uses: int = 1, xp_amount: int = 0) -> bool:
    existing = await get(session, code)
    if existing:
        return False
    promo = Promo(code=code, promo_type=promo_type, uses_left=uses,
                  used_by=[], xp_amount=xp_amount)
    session.add(promo)
    await session.flush()
    return True

async def delete(session: AsyncSession, code: str) -> bool:
    promo = await get(session, code)
    if not promo:
        return False
    from sqlalchemy import delete as sql_delete
    from db.models import Promo
    await session.execute(sql_delete(Promo).where(Promo.code == code))
    await session.flush()
    return True

async def use(session: AsyncSession, code: str, user_id: str) -> tuple[bool, str, Promo | None]:
    promo = await get(session, code)
    if not promo:
        return False, "promo_not_found", None
    if user_id in promo.used_by:
        return False, "already_used", None
    if promo.uses_left <= 0:
        return False, "exhausted", None
    promo.used_by = promo.used_by + [user_id]
    promo.uses_left -= 1
    await session.flush()
    return True, "", promo

async def list_all(session: AsyncSession) -> list[Promo]:
    r = await session.execute(select(Promo))
    return list(r.scalars().all())
