"""
services/promo_service.py — promo code service.
No Telegram imports. Each method manages its own DB session.
"""
from db.engine import get_session
from repositories import cabbit_repo, promo_repo
from core.constants import PROMO_TYPES, ACHIEVEMENTS
from core.game_math import apply_xp


def _apply_xp_to_cab(cab, amount: int) -> tuple[bool, int]:
    new_xp, new_level, leveled = apply_xp(cab.xp, cab.level, amount)
    cab.xp = new_xp
    cab.level = new_level
    stats = dict(cab.stats or {})
    stats["max_level"] = max(stats.get("max_level", 0), new_level)
    cab.stats = stats
    return leveled, new_level


def _check_achievements_cab(cab) -> list[dict]:
    stats = dict(cab.stats or {})
    stats["max_level"] = max(stats.get("max_level", 0), cab.level)
    cab.stats = stats
    earned = set(cab.achievements or [])
    new = []
    for ach in ACHIEVEMENTS:
        if ach["id"] not in earned and stats.get(ach["stat"], 0) >= ach["need"]:
            new.append(ach)
    return new


def _unlock_achievements_cab(cab, new_achs: list[dict]) -> int:
    earned = list(cab.achievements or [])
    total_xp = 0
    for ach in new_achs:
        earned.append(ach["id"])
        total_xp += ach["reward"]
    cab.achievements = earned
    return total_xp


async def use_promo(user_id: int, code: str) -> dict:
    """
    Activate a promo code.
    Returns {ok, error, promo_type, info, xp_gained, leveled_up, new_level,
             new_achievements, cabbit}
    """
    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return {"ok": False, "error": "not_found"}
        if cab.dead:
            return {"ok": False, "error": "dead"}

        code_upper = code.strip().upper()
        ok, err, promo = await promo_repo.use(s, code_upper, str(user_id))
        if not ok:
            return {"ok": False, "error": err}

        ptype = promo.promo_type
        info = PROMO_TYPES.get(ptype)
        if not info:
            return {"ok": False, "error": "unknown_type"}

        result = {"ok": True, "promo_type": ptype}

        if ptype == "жетон":
            cab.duel_tokens += 1
            await cabbit_repo.save(s, cab)
            result["duel_token"] = True
            result["cabbit_xp"] = cab.xp
            return result

        if ptype == "xp":
            xp_amount = promo.xp_amount
            if xp_amount <= 0:
                return {"ok": False, "error": "zero_xp"}
            leveled, new_level = _apply_xp_to_cab(cab, xp_amount)
            stats = dict(cab.stats or {})
            stats["xp_earned_total"] = stats.get("xp_earned_total", 0) + xp_amount
            cab.stats = stats

            new_achs = _check_achievements_cab(cab)
            if new_achs:
                bonus = _unlock_achievements_cab(cab, new_achs)
                _apply_xp_to_cab(cab, bonus)

            await cabbit_repo.save(s, cab)
            result["xp_gained"] = xp_amount
            result["leveled_up"] = leveled
            result["new_level"] = new_level
            result["new_achievements"] = new_achs if new_achs else []
            result["cabbit_xp"] = cab.xp
            return result

        # Food type promo
        food_name = info["food"]
        food_xp = info["xp"]
        leveled, new_level = _apply_xp_to_cab(cab, food_xp)
        counts = dict(cab.food_counts or {})
        counts[food_name] = counts.get(food_name, 0) + 1
        cab.food_counts = counts
        stats = dict(cab.stats or {})
        stats["xp_earned_total"] = stats.get("xp_earned_total", 0) + food_xp
        cab.stats = stats

        new_achs = _check_achievements_cab(cab)
        if new_achs:
            bonus = _unlock_achievements_cab(cab, new_achs)
            _apply_xp_to_cab(cab, bonus)

        await cabbit_repo.save(s, cab)

        result["food_name"] = food_name
        result["food_emoji"] = info["emoji"]
        result["xp_gained"] = food_xp
        result["leveled_up"] = leveled
        result["new_level"] = new_level
        result["new_achievements"] = new_achs if new_achs else []
        result["cabbit_xp"] = cab.xp
        return result


async def create_promo(code: str, promo_type: str, uses: int = 1,
                       xp_amount: int = 0) -> dict:
    """
    Create a new promo code (admin).
    Returns {ok, error}
    """
    if promo_type not in PROMO_TYPES:
        return {"ok": False, "error": "invalid_type",
                "valid_types": list(PROMO_TYPES.keys())}

    code_upper = code.strip().upper()
    async with get_session() as s:
        ok = await promo_repo.create(s, code_upper, promo_type, uses, xp_amount)
        if not ok:
            return {"ok": False, "error": "already_exists"}
        return {"ok": True, "code": code_upper, "promo_type": promo_type,
                "uses": uses, "xp_amount": xp_amount}


async def delete_promo(code: str) -> dict:
    """Delete a promo code (admin)."""
    code_upper = code.strip().upper()
    async with get_session() as s:
        ok = await promo_repo.delete(s, code_upper)
        if not ok:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "code": code_upper}


async def list_promos() -> dict:
    """List all promo codes (admin)."""
    async with get_session() as s:
        promos = await promo_repo.list_all(s)
        items = []
        for p in promos:
            info = PROMO_TYPES.get(p.promo_type, {})
            items.append({
                "code": p.code,
                "type": p.promo_type,
                "emoji": info.get("emoji", "?"),
                "uses_left": p.uses_left,
                "used_count": len(p.used_by or []),
                "xp_amount": p.xp_amount,
            })
        return {"ok": True, "promos": items}


async def get_promo(code: str) -> dict:
    """Get promo details (admin)."""
    code_upper = code.strip().upper()
    async with get_session() as s:
        promo = await promo_repo.get(s, code_upper)
        if not promo:
            return {"ok": False, "error": "not_found"}
        info = PROMO_TYPES.get(promo.promo_type, {})
        return {
            "ok": True,
            "code": promo.code,
            "type": promo.promo_type,
            "emoji": info.get("emoji", "?"),
            "uses_left": promo.uses_left,
            "used_by": promo.used_by or [],
            "used_count": len(promo.used_by or []),
            "xp_amount": promo.xp_amount,
        }
