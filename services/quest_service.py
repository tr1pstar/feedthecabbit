"""
services/quest_service.py — quests and achievements service.
No Telegram imports. Each method manages its own DB session.
"""
from db.engine import get_session
from repositories import cabbit_repo
from core.constants import ACHIEVEMENTS
from core.game_math import (
    apply_xp, get_or_refresh_quests, update_quest_progress,
)


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


async def get_quests(user_id: int) -> dict:
    """
    Get or refresh daily quests.
    Returns {ok, error, tasks, cabbit_xp}
    """
    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return {"ok": False, "error": "not_found"}
        if cab.dead:
            return {"ok": False, "error": "dead"}

        quest_data = dict(cab.quests or {})
        tasks, refreshed = get_or_refresh_quests(quest_data)
        if refreshed:
            from datetime import datetime
            quest_data["date"] = datetime.now().strftime("%Y-%m-%d")
            quest_data["tasks"] = tasks
        cab.quests = quest_data
        await cabbit_repo.save(s, cab)

        return {"ok": True, "tasks": tasks, "cabbit_xp": cab.xp}


async def claim_quest(user_id: int, quest_index: int) -> dict:
    """
    Claim a completed quest reward.
    Returns {ok, error, reward, leveled_up, new_level, new_achievements, cabbit_xp}
    """
    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return {"ok": False, "error": "not_found"}
        if cab.dead:
            return {"ok": False, "error": "dead"}

        quest_data = dict(cab.quests or {})
        tasks, refreshed = get_or_refresh_quests(quest_data)
        if refreshed:
            from datetime import datetime
            quest_data["date"] = datetime.now().strftime("%Y-%m-%d")
            quest_data["tasks"] = tasks

        if quest_index >= len(tasks):
            return {"ok": False, "error": "invalid_index"}

        task = tasks[quest_index]
        if task["claimed"]:
            return {"ok": False, "error": "already_claimed"}
        if task["progress"] < task["target"]:
            return {"ok": False, "error": "not_completed"}

        task["claimed"] = True
        reward = task["reward"]
        quest_data["tasks"] = tasks
        cab.quests = quest_data

        leveled, new_level = _apply_xp_to_cab(cab, reward)
        stats = dict(cab.stats or {})
        stats["xp_earned_total"] = stats.get("xp_earned_total", 0) + reward
        cab.stats = stats

        # Achievements
        new_achs = _check_achievements_cab(cab)
        if new_achs:
            bonus = _unlock_achievements_cab(cab, new_achs)
            _apply_xp_to_cab(cab, bonus)

        await cabbit_repo.save(s, cab)

        return {
            "ok": True,
            "reward": reward,
            "leveled_up": leveled,
            "new_level": new_level,
            "new_achievements": new_achs if new_achs else [],
            "cabbit_xp": cab.xp,
        }


async def get_achievements(user_id: int) -> dict:
    """
    Get achievements list with progress.
    Returns {ok, error, achievements, earned_count, total_count}
    """
    async with get_session() as s:
        cab = await cabbit_repo.get(s, user_id)
        if not cab:
            return {"ok": False, "error": "not_found"}
        if cab.dead:
            return {"ok": False, "error": "dead"}

        earned = set(cab.achievements or [])
        stats = cab.stats or {}
        items = []
        for ach in ACHIEVEMENTS:
            items.append({
                "id": ach["id"],
                "name": ach["name"],
                "emoji": ach["emoji"],
                "desc": ach["desc"],
                "stat": ach["stat"],
                "need": ach["need"],
                "reward": ach["reward"],
                "earned": ach["id"] in earned,
                "progress": stats.get(ach["stat"], 0),
            })
        return {
            "ok": True,
            "achievements": items,
            "earned_count": len(earned),
            "total_count": len(ACHIEVEMENTS),
        }
