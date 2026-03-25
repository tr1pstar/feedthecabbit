"""
services/skin_service.py — skin management service.
No Telegram imports. Each method manages its own DB session.
"""
import random

from db.engine import get_session
from repositories import cabbit_repo, skin_repo
from core.constants import RARITY_EMOJI, RARITY_ORDER, CAPSULE_PRICES, CAPSULE_NAMES


# ---------------------------------------------------------------------------
# Player methods
# ---------------------------------------------------------------------------

async def get_user_skins(user_id: int) -> dict:
    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return {"ok": False, "error": "not_found"}
        if cab.dead:
            return {"ok": False, "error": "dead"}

        owned_ids = await skin_repo.get_user_skins(s, user_id)
        all_skins = await skin_repo.get_all(s)
        skin_map = {sk.skin_id: sk for sk in all_skins}

        skins = []
        for sid in owned_ids:
            sk = skin_map.get(sid)
            if not sk:
                continue
            skins.append({
                "skin_id": sid,
                "display_name": sk.display_name,
                "rarity": sk.rarity,
                "rarity_emoji": RARITY_EMOJI.get(sk.rarity, "⚪"),
                "is_active": cab.skin == sid,
            })

        return {
            "ok": True,
            "skins": skins,
            "current_skin": cab.skin,
        }


async def select_skin(user_id: int, skin_id: str) -> dict:
    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return {"ok": False, "error": "not_found"}
        if cab.dead:
            return {"ok": False, "error": "dead"}

        if skin_id == "default":
            cab.skin = None
            await cabbit_repo.save(s, cab)
            return {"ok": True, "skin_name": "Стандартный"}

        owned_ids = await skin_repo.get_user_skins(s, user_id)
        if skin_id not in owned_ids:
            return {"ok": False, "error": "not_owned"}

        sk = await skin_repo.get(s, skin_id)
        if not sk:
            return {"ok": False, "error": "skin_not_found"}

        cab.skin = skin_id
        await cabbit_repo.save(s, cab)
        return {
            "ok": True,
            "skin_name": sk.display_name,
            "rarity_emoji": RARITY_EMOJI.get(sk.rarity, "⚪"),
        }


async def get_capsule_shop(user_id: int) -> dict:
    """
    Get capsule shop listing.
    Returns {ok, capsules, coins}
    capsules: list of {rarity, rarity_emoji, name, price, available_count, owned_all}
    """
    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return {"ok": False, "error": "not_found"}

        owned_ids = set(await skin_repo.get_user_skins(s, user_id))
        all_skins = await skin_repo.get_all(s)

        capsules = []
        for rarity in ["common", "rare", "epic", "legendary"]:
            price = CAPSULE_PRICES[rarity]
            name = CAPSULE_NAMES[rarity]
            r_em = RARITY_EMOJI[rarity]
            skins_of_rarity = [sk for sk in all_skins if sk.rarity == rarity]
            available = [sk for sk in skins_of_rarity if sk.skin_id not in owned_ids]
            capsules.append({
                "rarity": rarity,
                "rarity_emoji": r_em,
                "name": name,
                "price": price,
                "total_count": len(skins_of_rarity),
                "available_count": len(available),
                "owned_all": len(available) == 0 and len(skins_of_rarity) > 0,
            })

        return {"ok": True, "capsules": capsules, "coins": cab.coins}


async def buy_capsule(user_id: int, rarity: str) -> dict:
    """
    Buy a capsule of given rarity. Gives a random unowned skin of that rarity.
    Returns {ok, error, skin_name, skin_id, rarity_emoji, price, coins_left, file_id}
    """
    if rarity not in CAPSULE_PRICES:
        return {"ok": False, "error": "invalid_rarity"}

    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return {"ok": False, "error": "not_found"}
        if cab.dead:
            return {"ok": False, "error": "dead"}

        price = CAPSULE_PRICES[rarity]
        if cab.coins < price:
            return {"ok": False, "error": "insufficient_coins",
                    "coins": cab.coins, "price": price}

        # Get available skins of this rarity that user doesn't own
        owned_ids = set(await skin_repo.get_user_skins(s, user_id))
        skins_of_rarity = await skin_repo.get_by_rarity(s, rarity)
        available = [sk for sk in skins_of_rarity if sk.skin_id not in owned_ids]

        if not available:
            if not skins_of_rarity:
                return {"ok": False, "error": "no_skins_in_rarity"}
            return {"ok": False, "error": "all_owned"}

        # Random pick
        skin = random.choice(available)

        cab.coins -= price
        await cabbit_repo.save(s, cab)
        await skin_repo.add_user_skin(s, user_id, skin.skin_id)

        return {
            "ok": True,
            "skin_name": skin.display_name,
            "skin_id": skin.skin_id,
            "rarity": rarity,
            "rarity_emoji": RARITY_EMOJI.get(rarity, "⚪"),
            "price": price,
            "coins_left": cab.coins,
            "file_id": skin.file_id,
        }


async def get_skin_preview(skin_id: str) -> dict:
    async with get_session() as s:
        sk = await skin_repo.get(s, skin_id)
        if not sk:
            return {"ok": False, "error": "not_found"}
        return {
            "ok": True,
            "skin_id": sk.skin_id,
            "display_name": sk.display_name,
            "rarity": sk.rarity,
            "rarity_emoji": RARITY_EMOJI.get(sk.rarity, "⚪"),
            "shop_price": sk.shop_price,
            "file_id": sk.file_id,
        }


# ---------------------------------------------------------------------------
# Admin methods
# ---------------------------------------------------------------------------

async def admin_add_skin(skin_id: str, file_id: str, display_name: str,
                         rarity: str = "common", added_by: int = 0) -> dict:
    async with get_session() as s:
        existing = await skin_repo.get(s, skin_id)
        if existing:
            return {"ok": False, "error": "already_exists"}
        await skin_repo.add(s, skin_id, file_id, display_name, rarity, added_by)
        return {"ok": True, "skin_id": skin_id, "display_name": display_name, "rarity": rarity}


async def admin_set_drop_chance(skin_id: str, chance: float) -> dict:
    async with get_session() as s:
        ok = await skin_repo.update(s, skin_id, drop_chance=chance)
        if not ok:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "skin_id": skin_id, "drop_chance": chance}


async def admin_set_level_weight(skin_id: str, weight: int) -> dict:
    async with get_session() as s:
        ok = await skin_repo.update(s, skin_id, level_weight=weight)
        if not ok:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "skin_id": skin_id, "level_weight": weight}


async def admin_set_shop_price(skin_id: str, price: int) -> dict:
    async with get_session() as s:
        actual = price if price > 0 else None
        ok = await skin_repo.update(s, skin_id, shop_price=actual)
        if not ok:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "skin_id": skin_id, "shop_price": actual}


async def admin_remove_skin(skin_id: str) -> dict:
    async with get_session() as s:
        ok = await skin_repo.remove(s, skin_id)
        if not ok:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "skin_id": skin_id}


async def admin_give_skin(user_id: int, skin_id: str) -> dict:
    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return {"ok": False, "error": "user_not_found"}

        sk = await skin_repo.get(s, skin_id)
        if not sk:
            return {"ok": False, "error": "skin_not_found"}

        owned_ids = await skin_repo.get_user_skins(s, user_id)
        if skin_id in owned_ids:
            return {"ok": False, "error": "already_owned"}

        await skin_repo.add_user_skin(s, user_id, skin_id)
        return {
            "ok": True,
            "skin_name": sk.display_name,
            "rarity_emoji": RARITY_EMOJI.get(sk.rarity, "⚪"),
        }


async def admin_list_skins() -> dict:
    async with get_session() as s:
        all_skins = await skin_repo.get_all(s)
        items = []
        for sk in all_skins:
            items.append({
                "skin_id": sk.skin_id,
                "display_name": sk.display_name,
                "rarity": sk.rarity,
                "rarity_emoji": RARITY_EMOJI.get(sk.rarity, "⚪"),
                "drop_chance": sk.drop_chance,
                "level_weight": sk.level_weight,
                "shop_price": sk.shop_price,
                "added_by": sk.added_by,
                "file_id": sk.file_id,
            })
        return {"ok": True, "skins": items}
