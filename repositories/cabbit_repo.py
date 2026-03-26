from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Cabbit
import time

async def get(session: AsyncSession, user_id: int) -> Cabbit | None:
    return await session.get(Cabbit, user_id)

async def get_by_uid(session: AsyncSession, uid: int) -> Cabbit | None:
    r = await session.execute(select(Cabbit).where(Cabbit.uid == uid))
    return r.scalar_one_or_none()

async def create(session: AsyncSession, user_id: int, name: str) -> Cabbit:
    now = int(time.time())
    cabbit = Cabbit(
        user_id=user_id, name=name, xp=0, level=1, coins=0,
        box_available=True, box_ts=0, last_fed=now,
        warned_12h=False, warned_23h=False, dead=False,
        has_knife=False, food_counts={"Морковь": 0, "Корм": 0, "Вкусность": 0},
        duel_tokens=0, inventory={}, sick=False, sick_until=0,
        crown_boxes=0, last_raid=0, achievements=[], stats={},
        quests={}, prestige_stars=0, rules_accepted=False,
        banned=False,
    )
    session.add(cabbit)
    await session.flush()
    return cabbit

async def save(session: AsyncSession, cabbit: Cabbit) -> None:
    from sqlalchemy.orm.attributes import flag_modified
    for col in ("stats", "achievements", "inventory", "food_counts", "quests"):
        flag_modified(cabbit, col)
    session.add(cabbit)
    await session.flush()

async def delete(session: AsyncSession, user_id: int) -> None:
    from sqlalchemy import delete as sql_delete
    await session.execute(sql_delete(Cabbit).where(Cabbit.user_id == user_id))
    await session.flush()

async def get_all_alive(session: AsyncSession) -> list[Cabbit]:
    r = await session.execute(select(Cabbit).where(Cabbit.dead == False))
    return list(r.scalars().all())

async def get_all(session: AsyncSession) -> list[Cabbit]:
    r = await session.execute(select(Cabbit))
    return list(r.scalars().all())

async def get_knife_owner(session: AsyncSession) -> Cabbit | None:
    r = await session.execute(
        select(Cabbit).where(Cabbit.has_knife == True, Cabbit.dead == False).limit(1)
    )
    return r.scalar_one_or_none()

async def get_hungry_12h(session: AsyncSession, threshold: int) -> list[Cabbit]:
    r = await session.execute(
        select(Cabbit).where(
            Cabbit.dead == False, Cabbit.warned_12h == False,
            Cabbit.last_fed < threshold
        )
    )
    return list(r.scalars().all())

async def get_hungry_23h(session: AsyncSession, threshold: int) -> list[Cabbit]:
    r = await session.execute(
        select(Cabbit).where(
            Cabbit.dead == False, Cabbit.warned_23h == False,
            Cabbit.last_fed < threshold
        )
    )
    return list(r.scalars().all())

async def get_dying(session: AsyncSession, threshold: int) -> list[Cabbit]:
    r = await session.execute(
        select(Cabbit).where(Cabbit.dead == False, Cabbit.last_fed < threshold)
    )
    return list(r.scalars().all())

async def get_boxes_ready(session: AsyncSession, now: int) -> list[Cabbit]:
    r = await session.execute(
        select(Cabbit).where(
            Cabbit.dead == False, Cabbit.box_available == False, Cabbit.box_ts <= now
        )
    )
    return list(r.scalars().all())

async def get_leaderboard(session: AsyncSession, limit: int = 10) -> list[Cabbit]:
    r = await session.execute(
        select(Cabbit).where(Cabbit.dead == False)
        .order_by(Cabbit.prestige_stars.desc(), Cabbit.level.desc(), Cabbit.xp.desc())
        .limit(limit)
    )
    return list(r.scalars().all())

async def get_alive_uids(session: AsyncSession) -> list[int]:
    r = await session.execute(select(Cabbit.user_id).where(Cabbit.dead == False))
    return list(r.scalars().all())

async def get_alive_count(session: AsyncSession) -> int:
    r = await session.execute(select(func.count()).select_from(Cabbit).where(Cabbit.dead == False))
    return r.scalar_one()

async def get_others_alive(session: AsyncSession, exclude_uid: int) -> list[Cabbit]:
    r = await session.execute(
        select(Cabbit).where(Cabbit.dead == False, Cabbit.user_id != exclude_uid)
    )
    return list(r.scalars().all())

async def get_referrals(session: AsyncSession, user_id: int) -> list[Cabbit]:
    r = await session.execute(
        select(Cabbit).where(Cabbit.referred_by == user_id)
    )
    return list(r.scalars().all())


async def get_others_with_xp(session: AsyncSession, exclude_uid: int) -> list[Cabbit]:
    r = await session.execute(
        select(Cabbit).where(Cabbit.dead == False, Cabbit.user_id != exclude_uid, Cabbit.xp > 0)
    )
    return list(r.scalars().all())
