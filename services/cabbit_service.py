"""
services/cabbit_service.py — main game service for cabbit operations.
No Telegram imports. Each method manages its own DB session.
"""
import random
import time

from db.engine import get_session
from repositories import cabbit_repo, skin_repo, duel_repo
from core.constants import (
    FOOD_TABLE, FOOD_HEAL, KNIFE_CHANCE, ITEM_TABLE, SICKNESS_CHANCE,
    SICKNESS_DURATION, RAID_COOLDOWN, SKIN_LEVEL_INTERVAL, COINS_PER_BOX,
    COINS_DAILY_BONUS, COINS_RAID_OK, RARITY_EMOJI, ACHIEVEMENTS,
    RENAME_COST, WARN_12H, WARN_23H,
)
from core.game_math import (
    xp_for_level, get_evolution, get_box_interval, roll_box, roll_item,
    roll_event, check_sickness, apply_xp, do_prestige as _do_prestige_math,
    roll_skin_drop, roll_skin_level, check_achievements, unlock_achievements,
    get_or_refresh_quests, update_quest_progress, hunger_percent,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _cabbit_to_dict(cab) -> dict:
    return {
        "uid": cab.uid,
        "user_id": cab.user_id,
        "name": cab.name,
        "xp": cab.xp,
        "level": cab.level,
        "coins": cab.coins,
        "box_available": cab.box_available,
        "box_ts": cab.box_ts,
        "last_fed": cab.last_fed,
        "warned_12h": cab.warned_12h,
        "warned_23h": cab.warned_23h,
        "dead": cab.dead,
        "has_knife": cab.has_knife,
        "food_counts": cab.food_counts or {},
        "duel_tokens": cab.duel_tokens,
        "inventory": cab.inventory or {},
        "sick": cab.sick,
        "sick_until": cab.sick_until,
        "crown_boxes": cab.crown_boxes,
        "last_raid": cab.last_raid,
        "achievements": cab.achievements or [],
        "stats": cab.stats or {},
        "quests": cab.quests or {},
        "prestige_stars": cab.prestige_stars,
        "skin": cab.skin,
        "rules_accepted": cab.rules_accepted,
        "banned": cab.banned,
        "ban_reason": cab.ban_reason,
        "last_box_day": cab.last_box_day,
        "banned_by": cab.banned_by,
        "banned_at": cab.banned_at,
    }


def _apply_xp_to_cab(cab, amount: int) -> tuple[bool, int]:
    new_xp, new_level, leveled = apply_xp(cab.xp, cab.level, amount)
    cab.xp = new_xp
    cab.level = new_level
    stats = dict(cab.stats or {})
    stats["max_level"] = max(stats.get("max_level", 0), new_level)
    cab.stats = stats
    return leveled, new_level


def _check_and_cure_sickness(cab) -> bool:
    if not cab.sick:
        return False
    if int(time.time()) >= cab.sick_until:
        cab.sick = False
        cab.sick_until = 0
        return False
    return True


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


def _update_quest_progress_cab(cab, action: str, amount: int = 1):
    quest_data = dict(cab.quests or {})
    tasks, refreshed = get_or_refresh_quests(quest_data)
    if refreshed:
        from datetime import datetime
        quest_data["date"] = datetime.now().strftime("%Y-%m-%d")
        quest_data["tasks"] = tasks
    update_quest_progress(tasks, action, amount)
    quest_data["tasks"] = tasks
    cab.quests = quest_data


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

async def get_cabbit(user_id: int) -> dict | None:
    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return None
        _check_and_cure_sickness(cab)
        await cabbit_repo.save(s, cab)
        return _cabbit_to_dict(cab)


async def get_user_id_by_uid(uid: int) -> int | None:
    async with get_session() as s:
        cab = await cabbit_repo.get_by_uid(s, uid)
        return cab.user_id if cab else None


async def create_cabbit(user_id: int, name: str) -> dict:
    async with get_session() as s:
        cab = await cabbit_repo.create(s, user_id, name)
        cab.rules_accepted = True
        await cabbit_repo.save(s, cab)
        return _cabbit_to_dict(cab)


async def accept_rules(user_id: int) -> dict | None:
    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return None
        cab.rules_accepted = True
        _check_and_cure_sickness(cab)
        await cabbit_repo.save(s, cab)
        return _cabbit_to_dict(cab)


async def delete_cabbit(user_id: int) -> bool:
    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return False
        await cabbit_repo.delete(s, user_id)
        return True


async def rename_cabbit(user_id: int, new_name: str) -> dict:
    """
    Rename cabbit for RENAME_COST coins.
    Returns {ok, error, old_name, new_name, coins_left}
    """
    if not new_name or len(new_name) > 20:
        return {"ok": False, "error": "invalid_name"}

    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return {"ok": False, "error": "not_found"}
        if cab.dead:
            return {"ok": False, "error": "dead"}
        if cab.coins < RENAME_COST:
            return {"ok": False, "error": "insufficient_coins",
                    "coins": cab.coins, "cost": RENAME_COST}

        old_name = cab.name
        cab.name = new_name
        cab.coins -= RENAME_COST
        await cabbit_repo.save(s, cab)

        return {
            "ok": True,
            "old_name": old_name,
            "new_name": new_name,
            "coins_left": cab.coins,
        }


async def open_box(user_id: int) -> dict:
    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return {"ok": False, "error": "not_found"}
        if cab.dead:
            return {"ok": False, "error": "dead"}

        # Block if in active duel
        duel = await duel_repo.find_by_user(s, user_id)
        if duel and duel.status == "active":
            return {"ok": False, "error": "in_duel"}

        now = int(time.time())
        if not (cab.box_available or now >= cab.box_ts):
            return {"ok": False, "error": "cooldown"}

        result = {"ok": True}

        # Stats
        stats = dict(cab.stats or {})
        stats["boxes_opened"] = stats.get("boxes_opened", 0) + 1
        cab.stats = stats

        is_sick = _check_and_cure_sickness(cab)
        evo = get_evolution(cab.level)
        box_cd = evo["box_cd"]

        knife_owner = await cabbit_repo.get_knife_owner(s)
        knife_exists = knife_owner is not None

        food_name, food_emoji, food_xp, got_knife = roll_box(knife_exists)
        item_drop = roll_item()
        event = roll_event()
        actual_xp = 0

        result["food_name"] = food_name
        result["food_emoji"] = food_emoji
        result["got_knife"] = got_knife
        result["crown_active"] = False
        result["sick_debuff"] = False

        if got_knife:
            cab.has_knife = True
            alive_uids = await cabbit_repo.get_alive_uids(s)
            result["notify_knife_uids"] = [u for u in alive_uids if u != user_id]
            result["leveled_up"] = False
            result["new_level"] = cab.level
            result["xp_mult"] = 1.0
            result["new_evo"] = None
            result["is_sick"] = False
        else:
            result["notify_knife_uids"] = []
            xp_mult = evo["xp_mult"] + cab.prestige_stars * 0.1

            if cab.crown_boxes > 0:
                xp_mult *= 2
                cab.crown_boxes -= 1
                result["crown_active"] = True

            if is_sick:
                xp_mult *= 0.5
                result["sick_debuff"] = True

            actual_xp = int(food_xp * xp_mult)
            leveled, new_level = _apply_xp_to_cab(cab, actual_xp)

            counts = dict(cab.food_counts or {})
            counts[food_name] = counts.get(food_name, 0) + 1
            cab.food_counts = counts

            stats = dict(cab.stats or {})
            stats["xp_earned_total"] = stats.get("xp_earned_total", 0) + actual_xp
            cab.stats = stats

            result["xp_mult"] = xp_mult
            result["leveled_up"] = leveled
            result["new_level"] = new_level

            # Evolution change
            new_evo = get_evolution(new_level) if leveled else evo
            result["evolution"] = new_evo if leveled and new_evo != evo else None

            # Skin for level-up
            result["skin_level"] = None
            if leveled and new_level % SKIN_LEVEL_INTERVAL == 0:
                owned_skins = await skin_repo.get_user_skins(s, user_id)
                level_pool_skins = await skin_repo.get_level_pool(s)
                pool = [(sk.skin_id, {"level_weight": sk.level_weight, "display_name": sk.display_name,
                                       "rarity": sk.rarity}) for sk in level_pool_skins]
                lvl_skin = roll_skin_level(pool, owned_skins)
                if lvl_skin:
                    s_id, s_data = lvl_skin
                    if s_id not in owned_skins:
                        await skin_repo.add_user_skin(s, user_id, s_id)
                    result["skin_level"] = {"skin_id": s_id, **s_data}
                else:
                    bonus_coins = 50
                    cab.coins += bonus_coins
                    result["skin_level_coins"] = bonus_coins

        result["actual_xp"] = actual_xp
        result["food_xp"] = food_xp

        # Coins
        coin_gain = random.randint(*COINS_PER_BOX)
        today = time.strftime("%Y-%m-%d")
        daily_bonus = False
        if cab.last_box_day != today:
            coin_gain += COINS_DAILY_BONUS
            cab.last_box_day = today
            daily_bonus = True
        cab.coins += coin_gain
        result["coins_gained"] = coin_gain
        result["daily_bonus"] = daily_bonus

        # Skin drop from box
        result["skin_drop"] = None
        if not got_knife:
            owned_skins = await skin_repo.get_user_skins(s, user_id)
            droppable_skins = await skin_repo.get_droppable(s)
            droppable = [(sk.skin_id, {"drop_chance": sk.drop_chance, "display_name": sk.display_name,
                                        "rarity": sk.rarity}) for sk in droppable_skins]
            skin_drop = roll_skin_drop(droppable, owned_skins)
            if skin_drop:
                s_id, s_data = skin_drop
                if s_id not in owned_skins:
                    await skin_repo.add_user_skin(s, user_id, s_id)
                result["skin_drop"] = {"skin_id": s_id, **s_data}

        # Item drop
        result["item"] = None
        if item_drop:
            item_name, item_emoji = item_drop
            inv = dict(cab.inventory or {})
            if item_name == "Корона":
                cab.crown_boxes = cab.crown_boxes + 3
            else:
                inv[item_name] = inv.get(item_name, 0) + 1
                cab.inventory = inv
            result["item"] = {"name": item_name, "emoji": item_emoji}

        # Random event
        result["event"] = None
        if event:
            result["event"] = dict(event)
            if event.get("xp"):
                ev_xp = event["xp"]
                if ev_xp > 0:
                    _apply_xp_to_cab(cab, ev_xp)
                    stats = dict(cab.stats or {})
                    stats["xp_earned_total"] = stats.get("xp_earned_total", 0) + ev_xp
                    cab.stats = stats
                else:
                    cab.xp = max(0, cab.xp + ev_xp)
            if event.get("tokens"):
                cab.duel_tokens += event["tokens"]
            if event.get("level_up"):
                cab.level += 1
                cab.xp = 0
                stats = dict(cab.stats or {})
                stats["max_level"] = max(stats.get("max_level", 0), cab.level)
                cab.stats = stats

        # Sickness roll
        result["sickness_roll"] = False
        if not got_knife and not cab.sick and random.randint(1, 100) <= SICKNESS_CHANCE:
            cab.sick = True
            cab.sick_until = now + SICKNESS_DURATION
            result["sickness_roll"] = True

        # Common updates
        cab.box_available = False
        cab.box_ts = now + box_cd
        if not got_knife:
            heal = FOOD_HEAL.get(food_name, 3 * 3600)
            cab.last_fed = min(now, cab.last_fed + heal)
        elapsed_after = now - cab.last_fed
        # FIX: use WARN_12H/WARN_23H thresholds (not FOOD_HEAL values)
        if elapsed_after < WARN_12H:
            cab.warned_12h = False
        if elapsed_after < WARN_23H:
            cab.warned_23h = False
        cab.duel_tokens += 1

        # Quest progress
        _update_quest_progress_cab(cab, "open_boxes")
        if not got_knife:
            _update_quest_progress_cab(cab, "feed_cabbit")
            _update_quest_progress_cab(cab, "earn_xp", actual_xp)

        # Achievements
        new_achs = _check_achievements_cab(cab)
        result["new_achievements"] = []
        if new_achs:
            bonus = _unlock_achievements_cab(cab, new_achs)
            _apply_xp_to_cab(cab, bonus)
            result["new_achievements"] = new_achs

        await cabbit_repo.save(s, cab)
        result["cabbit"] = _cabbit_to_dict(cab)
        return result


async def use_item(user_id: int, item: str) -> dict:
    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return {"ok": False, "error": "not_found"}
        if cab.dead:
            return {"ok": False, "error": "dead"}

        inv = dict(cab.inventory or {})
        if inv.get(item, 0) <= 0:
            return {"ok": False, "error": "no_item"}

        inv[item] -= 1
        cab.inventory = inv
        result = {"ok": True, "effect": item}

        if item == "Зелье":
            cab.last_fed = int(time.time())
            cab.warned_12h = False
            cab.warned_23h = False

        elif item == "Таблетка":
            cab.sick = False
            cab.sick_until = 0

        elif item == "Магнит":
            others = await cabbit_repo.get_others_with_xp(s, user_id)
            if not others:
                inv[item] += 1
                cab.inventory = inv
                await cabbit_repo.save(s, cab)
                return {"ok": False, "error": "no_targets"}

            target = random.choice(others)
            stolen = random.randint(100, 300)
            stolen = min(stolen, target.xp)
            target.xp = max(0, target.xp - stolen)
            leveled, new_level = _apply_xp_to_cab(cab, stolen)
            stats = dict(cab.stats or {})
            stats["xp_earned_total"] = stats.get("xp_earned_total", 0) + stolen
            cab.stats = stats
            await cabbit_repo.save(s, target)

            result["stolen_xp"] = stolen
            result["target_name"] = target.name
            result["target_uid"] = target.user_id
            result["leveled_up"] = leveled
            result["new_level"] = new_level

        await cabbit_repo.save(s, cab)
        result["cabbit"] = _cabbit_to_dict(cab)
        return result


async def do_prestige(user_id: int) -> dict:
    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return {"ok": False, "error": "not_found"}
        if cab.dead:
            return {"ok": False, "error": "dead"}
        if cab.level < 30:
            return {"ok": False, "error": "low_level", "level": cab.level}

        stars, reset = _do_prestige_math(cab.prestige_stars)
        for key, val in reset.items():
            setattr(cab, key, val)
        await cabbit_repo.save(s, cab)
        return {"ok": True, "stars": stars, "cabbit": _cabbit_to_dict(cab)}


async def do_raid(user_id: int) -> dict:
    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return {"ok": False, "error": "not_found"}
        if cab.dead:
            return {"ok": False, "error": "dead"}

        # Block if in active duel
        duel = await duel_repo.find_by_user(s, user_id)
        if duel and duel.status == "active":
            return {"ok": False, "error": "in_duel"}

        now = int(time.time())
        if now < cab.last_raid + RAID_COOLDOWN:
            left = cab.last_raid + RAID_COOLDOWN - now
            return {"ok": False, "error": "cooldown", "seconds_left": left}

        others = await cabbit_repo.get_others_with_xp(s, user_id)
        if not others:
            return {"ok": False, "error": "no_targets"}

        target = random.choice(others)
        cab.last_raid = now
        stats = dict(cab.stats or {})
        result = {"ok": True}

        _update_quest_progress_cab(cab, "do_raid")

        if random.randint(1, 100) <= 40:
            stolen = max(1, int(target.xp * 0.1))
            stolen = min(stolen, 500)
            target.xp = max(0, target.xp - stolen)
            leveled, new_level = _apply_xp_to_cab(cab, stolen)
            stats["raids_ok"] = stats.get("raids_ok", 0) + 1
            stats["xp_earned_total"] = stats.get("xp_earned_total", 0) + stolen
            cab.coins += COINS_RAID_OK
            await cabbit_repo.save(s, target)

            result["success"] = True
            result["stolen"] = stolen
            result["target_name"] = target.name
            result["target_uid"] = target.user_id
            result["leveled_up"] = leveled
            result["new_level"] = new_level
            result["coins_gained"] = COINS_RAID_OK
        else:
            lost = max(1, int(cab.xp * 0.05))
            cab.xp = max(0, cab.xp - lost)
            stats["raids_fail"] = stats.get("raids_fail", 0) + 1

            result["success"] = False
            result["lost"] = lost
            result["target_name"] = target.name

        cab.stats = stats

        # Achievements
        new_achs = _check_achievements_cab(cab)
        result["new_achievements"] = []
        if new_achs:
            bonus = _unlock_achievements_cab(cab, new_achs)
            _apply_xp_to_cab(cab, bonus)
            result["new_achievements"] = new_achs

        await cabbit_repo.save(s, cab)
        result["cabbit"] = _cabbit_to_dict(cab)
        return result


async def kill_cabbit(attacker_id: int, target_id: int) -> dict:
    async with get_session() as s:
        attacker = await cabbit_repo.get(s, attacker_id)
        target = await cabbit_repo.get(s, target_id)

        if not attacker or not attacker.has_knife:
            return {"ok": False, "error": "no_knife"}
        if not target or target.dead:
            return {"ok": False, "error": "target_dead"}

        target_name = target.name
        attacker_name = attacker.name
        result = {"ok": True, "target_name": target_name, "attacker_name": attacker_name,
                  "target_uid": target_id, "attacker_uid": attacker_id}

        inv = dict(target.inventory or {})
        if inv.get("Щит", 0) > 0:
            inv["Щит"] -= 1
            target.inventory = inv
            attacker.has_knife = False
            await cabbit_repo.save(s, target)
            await cabbit_repo.save(s, attacker)
            result["shielded"] = True
            result["killed"] = False
            result["cabbit"] = _cabbit_to_dict(attacker)
            return result

        target.dead = True
        await cabbit_repo.save(s, target)

        attacker.has_knife = False
        stats = dict(attacker.stats or {})
        stats["kills"] = stats.get("kills", 0) + 1
        attacker.stats = stats

        new_achs = _check_achievements_cab(attacker)
        result["new_achievements"] = []
        if new_achs:
            bonus = _unlock_achievements_cab(attacker, new_achs)
            _apply_xp_to_cab(attacker, bonus)
            result["new_achievements"] = new_achs

        await cabbit_repo.save(s, attacker)

        alive_uids = await cabbit_repo.get_alive_uids(s)
        result["broadcast_uids"] = [u for u in alive_uids if u not in (attacker_id, target_id)]
        result["shielded"] = False
        result["killed"] = True
        result["cabbit"] = _cabbit_to_dict(attacker)
        return result


async def get_leaderboard(limit: int = 10) -> list[dict]:
    async with get_session() as s:
        cabs = await cabbit_repo.get_leaderboard(s, limit)
        return [_cabbit_to_dict(c) for c in cabs]


async def get_all_cabbits() -> list[dict]:
    async with get_session() as s:
        cabs = await cabbit_repo.get_all(s)
        return [_cabbit_to_dict(c) for c in cabs]


async def get_alive_uids() -> list[int]:
    async with get_session() as s:
        return await cabbit_repo.get_alive_uids(s)


async def ban_cabbit(target_id: int, admin_id: int, reason: str) -> dict:
    async with get_session() as s:
        cab = await cabbit_repo.get(s, target_id)
        if not cab:
            return {"ok": False, "error": "not_found"}
        if cab.dead:
            return {"ok": False, "error": "already_dead"}
        if cab.banned:
            return {"ok": False, "error": "already_banned"}

        target_name = cab.name
        cab.dead = True
        cab.banned = True
        cab.ban_reason = reason
        cab.banned_by = admin_id
        cab.banned_at = int(time.time())
        await cabbit_repo.save(s, cab)
        return {"ok": True, "target_name": target_name, "cabbit": _cabbit_to_dict(cab)}


async def add_xp(target_id: int, amount: int) -> dict:
    async with get_session() as s:
        cab = await cabbit_repo.get(s, target_id)
        if not cab:
            return {"ok": False, "error": "not_found"}
        if cab.dead:
            return {"ok": False, "error": "dead"}

        old_level = cab.level
        if amount > 0:
            leveled, new_level = _apply_xp_to_cab(cab, amount)
        else:
            cab.xp = max(0, cab.xp + amount)
            new_level = cab.level
            leveled = False

        await cabbit_repo.save(s, cab)
        return {
            "ok": True, "old_level": old_level, "new_level": new_level,
            "leveled_up": leveled, "name": cab.name,
            "cabbit": _cabbit_to_dict(cab),
        }


async def add_coins(target_id: int, amount: int) -> dict:
    async with get_session() as s:
        cab = await cabbit_repo.get(s, target_id)
        if not cab:
            return {"ok": False, "error": "not_found"}

        cab.coins = max(0, cab.coins + amount)
        await cabbit_repo.save(s, cab)
        return {"ok": True, "name": cab.name, "cabbit": _cabbit_to_dict(cab)}


async def get_skin_file_id(cabbit_dict: dict) -> str | None:
    skin_id = cabbit_dict.get("skin")
    if not skin_id:
        return None
    async with get_session() as s:
        skin = await skin_repo.get(s, skin_id)
        if skin:
            return skin.file_id
        return None
