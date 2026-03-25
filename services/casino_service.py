"""
services/casino_service.py — casino slot machine service.
No Telegram imports. Each method manages its own DB session.
"""
from db.engine import get_session
from repositories import cabbit_repo, duel_repo
from core.constants import ACHIEVEMENTS
from core.game_math import spin_slots, apply_xp, get_or_refresh_quests, update_quest_progress


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


async def play_casino(user_id: int, bet: int) -> dict:
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

        if cab.xp < bet:
            return {"ok": False, "error": "insufficient_xp", "xp": cab.xp}
        if bet < 1:
            return {"ok": False, "error": "min_bet"}
        if bet > 5000:
            return {"ok": False, "error": "max_bet"}

        symbols, mult = spin_slots()
        stats = dict(cab.stats or {})
        result = {"ok": True, "symbols": symbols, "multiplier": mult}

        _update_quest_progress_cab(cab, "use_casino")

        if mult > 0:
            win = int(bet * mult)
            net = win - bet
            leveled, new_level = _apply_xp_to_cab(cab, net)
            stats["casino_wins"] = stats.get("casino_wins", 0) + 1
            stats["xp_earned_total"] = stats.get("xp_earned_total", 0) + net
            cab.stats = stats

            result["won"] = True
            result["net_xp"] = net
            result["leveled_up"] = leveled
            result["new_level"] = new_level
        else:
            cab.xp = max(0, cab.xp - bet)
            stats["casino_losses"] = stats.get("casino_losses", 0) + 1
            cab.stats = stats

            result["won"] = False
            result["net_xp"] = -bet
            result["leveled_up"] = False
            result["new_level"] = cab.level

        # Achievements
        new_achs = _check_achievements_cab(cab)
        result["new_achievements"] = []
        if new_achs:
            bonus = _unlock_achievements_cab(cab, new_achs)
            _apply_xp_to_cab(cab, bonus)
            result["new_achievements"] = new_achs

        await cabbit_repo.save(s, cab)

        result["cabbit"] = {
            "user_id": cab.user_id, "name": cab.name, "xp": cab.xp,
            "level": cab.level, "coins": cab.coins,
        }
        return result
