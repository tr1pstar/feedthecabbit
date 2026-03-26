from sqlalchemy import select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Skin, UserSkin
import time

async def get(session: AsyncSession, skin_id: str) -> Skin | None:
    return await session.get(Skin, skin_id)

async def get_all(session: AsyncSession) -> list[Skin]:
    r = await session.execute(select(Skin))
    return list(r.scalars().all())

async def add(session: AsyncSession, skin_id: str, file_id: str,
              display_name: str, rarity: str = "common", added_by: int = 0) -> Skin:
    skin = Skin(skin_id=skin_id, file_id=file_id, display_name=display_name,
                rarity=rarity, added_by=added_by, added_at=int(time.time()))
    session.add(skin)
    await session.flush()
    return skin

async def update(session: AsyncSession, skin_id: str, **fields) -> bool:
    skin = await get(session, skin_id)
    if not skin:
        return False
    for k, v in fields.items():
        setattr(skin, k, v)
    await session.flush()
    return True

async def remove(session: AsyncSession, skin_id: str) -> bool:
    skin = await get(session, skin_id)
    if not skin:
        return False
    from sqlalchemy import delete as sql_delete
    from db.models import Skin
    await session.execute(sql_delete(Skin).where(Skin.skin_id == skin_id))
    await session.flush()
    return True

async def get_droppable(session: AsyncSession) -> list[Skin]:
    r = await session.execute(select(Skin).where(Skin.drop_chance > 0))
    return list(r.scalars().all())

async def get_level_pool(session: AsyncSession) -> list[Skin]:
    r = await session.execute(select(Skin).where(Skin.level_weight > 0))
    return list(r.scalars().all())

async def get_shop(session: AsyncSession) -> list[Skin]:
    r = await session.execute(
        select(Skin).where(Skin.shop_price.isnot(None), Skin.shop_price > 0)
    )
    skins = list(r.scalars().all())
    order = {"common": 0, "rare": 1, "epic": 2, "legendary": 3}
    skins.sort(key=lambda s: order.get(s.rarity, 0))
    return skins

async def get_by_rarity(session: AsyncSession, rarity: str) -> list[Skin]:
    """Get all skins of a specific rarity."""
    r = await session.execute(select(Skin).where(Skin.rarity == rarity))
    return list(r.scalars().all())

async def get_user_skins(session: AsyncSession, user_id: int) -> list[str]:
    r = await session.execute(select(UserSkin.skin_id).where(UserSkin.user_id == user_id))
    return list(r.scalars().all())

async def add_user_skin(session: AsyncSession, user_id: int, skin_id: str) -> None:
    session.add(UserSkin(user_id=user_id, skin_id=skin_id))
    await session.flush()

async def has_skin(session: AsyncSession, user_id: int, skin_id: str) -> bool:
    r = await session.execute(
        select(UserSkin).where(UserSkin.user_id == user_id, UserSkin.skin_id == skin_id).limit(1)
    )
    return r.scalar_one_or_none() is not None

async def delete_all_user_skins(session: AsyncSession) -> int:
    """Delete all user_skins (for season wipe). Returns count deleted."""
    r = await session.execute(sql_delete(UserSkin))
    await session.flush()
    return r.rowcount
