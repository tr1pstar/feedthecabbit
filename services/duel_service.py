"""
services/duel_service.py — duel (RPS) service.
No Telegram imports. Each method manages its own DB session.
"""
from db.engine import get_session
from repositories import cabbit_repo, duel_repo
from core.constants import BEATS, ACHIEVEMENTS
from core.game_math import (
    apply_xp, resolve_duel_move, get_or_refresh_quests, update_quest_progress,
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


def _update_quest_progress_cab(cab, action: str, amount: int = 1):
    from sqlalchemy.orm.attributes import flag_modified
    quest_data = dict(cab.quests or {})
    tasks, refreshed = get_or_refresh_quests(quest_data)
    if refreshed:
        from datetime import datetime
        quest_data["date"] = datetime.now().strftime("%Y-%m-%d")
        quest_data["tasks"] = tasks
    update_quest_progress(tasks, action, amount)
    quest_data["tasks"] = tasks
    cab.quests = quest_data
    flag_modified(cab, "quests")


async def is_in_duel(user_id: int) -> bool:
    """Check if user is currently in any active/pending duel."""
    async with get_session() as s:
        duel = await duel_repo.find_by_user(s, user_id)
        return duel is not None


async def send_challenge(challenger_id: int, target_id: int, stake: int) -> dict:
    async with get_session() as s:
        c_cab = await cabbit_repo.get(s, challenger_id)
        t_cab = await cabbit_repo.get(s, target_id)

        if not c_cab or c_cab.dead:
            return {"ok": False, "error": "challenger_dead"}
        if not t_cab or t_cab.dead:
            return {"ok": False, "error": "target_dead"}
        if c_cab.duel_tokens <= 0:
            return {"ok": False, "error": "no_tokens"}
        if c_cab.xp < stake:
            return {"ok": False, "error": "challenger_insufficient_xp"}
        if t_cab.xp < stake:
            return {"ok": False, "error": "target_insufficient_xp"}
        if stake < 1:
            return {"ok": False, "error": "min_stake"}

        # Check for existing duel for either player
        existing_c = await duel_repo.find_by_user(s, challenger_id)
        if existing_c:
            return {"ok": False, "error": "duel_exists"}
        existing_t = await duel_repo.find_by_user(s, target_id)
        if existing_t:
            return {"ok": False, "error": "target_in_duel"}

        c_cab.duel_tokens -= 1
        await cabbit_repo.save(s, c_cab)
        await duel_repo.create(s, challenger_id, target_id, stake)

        return {
            "ok": True,
            "challenger_name": c_cab.name,
            "target_name": t_cab.name,
            "stake": stake,
        }


async def accept_duel(challenger_id: int, acceptor_id: int) -> dict:
    async with get_session() as s:
        duel = await duel_repo.get(s, challenger_id)
        if not duel or duel.status != "pending" or duel.target_id != acceptor_id:
            return {"ok": False, "error": "invalid_duel"}

        c_cab = await cabbit_repo.get(s, challenger_id)
        t_cab = await cabbit_repo.get(s, acceptor_id)

        if not c_cab or c_cab.dead or not t_cab or t_cab.dead:
            await duel_repo.delete(s, challenger_id)
            if c_cab and not c_cab.dead:
                c_cab.duel_tokens += 1
                await cabbit_repo.save(s, c_cab)
            return {"ok": False, "error": "cabbit_dead"}

        import time as _time
        from sqlalchemy.orm.attributes import flag_modified
        duel.status = "active"
        duel.moves = {}
        duel.round_started_at = int(_time.time())
        flag_modified(duel, "moves")
        await duel_repo.save(s, duel)

        return {
            "ok": True,
            "challenger_name": c_cab.name,
            "target_name": t_cab.name,
            "stake": duel.stake,
        }


async def decline_duel(challenger_id: int, decliner_id: int) -> dict:
    async with get_session() as s:
        duel = await duel_repo.get(s, challenger_id)
        if not duel or duel.target_id != decliner_id:
            return {"ok": False, "error": "invalid"}

        await duel_repo.delete(s, challenger_id)

        c_cab = await cabbit_repo.get(s, challenger_id)
        t_cab = await cabbit_repo.get(s, decliner_id)
        decliner_name = t_cab.name if t_cab else "Противник"

        if c_cab:
            c_cab.duel_tokens += 1
            await cabbit_repo.save(s, c_cab)

        return {
            "ok": True,
            "challenger_name": c_cab.name if c_cab else "?",
            "decliner_name": decliner_name,
        }


async def make_move(challenger_id: int, player_id: int, move: str) -> dict:
    from sqlalchemy import text
    import time as _time

    player_key = str(player_id)

    async with get_session() as s:
        # Single atomic UPDATE: add move only if player hasn't moved yet
        # Returns the updated moves dict
        import json
        move_patch = json.dumps({player_key: move})
        result = await s.execute(
            text("""
                UPDATE duels
                SET moves = moves || cast(:patch as jsonb)
                WHERE challenger_id = :cid
                  AND status = 'active'
                  AND NOT (moves \\? :pkey)
                RETURNING target_id, stake, moves
            """),
            {"patch": move_patch, "pkey": player_key, "cid": challenger_id},
        )
        row = result.mappings().first()

        if not row:
            # Either duel doesn't exist, not active, or already moved
            # Check which case
            check = await s.execute(
                text("SELECT status, moves, target_id FROM duels WHERE challenger_id = :cid"),
                {"cid": challenger_id},
            )
            check_row = check.mappings().first()
            if not check_row or check_row["status"] != "active":
                return {"ok": False, "error": "no_active_duel"}
            if player_id not in (challenger_id, check_row["target_id"]):
                return {"ok": False, "error": "not_participant"}
            if player_key in (check_row["moves"] or {}):
                return {"ok": False, "error": "already_moved"}
            return {"ok": False, "error": "no_active_duel"}

        target_id = row["target_id"]
        if player_id not in (challenger_id, target_id):
            return {"ok": False, "error": "not_participant"}

        moves = dict(row["moves"])
        stake = row["stake"]

        if len(moves) < 2:
            await s.commit()
            return {"ok": True, "waiting": True, "resolved": False, "move": move}

        # Both moves in — resolve
        c_move = moves[str(challenger_id)]
        t_move = moves[str(target_id)]

        c_cab = await cabbit_repo.get(s, challenger_id)
        t_cab = await cabbit_repo.get(s, target_id)
        c_name = c_cab.name if c_cab else "?"
        t_name = t_cab.name if t_cab else "?"

        outcome = resolve_duel_move(c_move, t_move)

        if outcome == "tie":
            await s.execute(
                text("UPDATE duels SET moves = '{}', round_started_at = :ts WHERE challenger_id = :cid"),
                {"ts": int(_time.time()), "cid": challenger_id},
            )
            return {
                "ok": True, "waiting": False, "resolved": True,
                "result": {
                    "tie": True, "c_move": c_move, "t_move": t_move,
                    "challenger_name": c_name, "target_name": t_name,
                },
            }

        # Winner determined — finish
        await s.execute(
            text("DELETE FROM duels WHERE challenger_id = :cid"),
            {"cid": challenger_id},
        )

        if not c_cab or not t_cab or c_cab.dead or t_cab.dead:
            return {
                "ok": True, "waiting": False, "resolved": True,
                "result": {
                    "tie": False, "cancelled": True,
                    "c_move": c_move, "t_move": t_move,
                    "challenger_name": c_name, "target_name": t_name,
                },
            }

        if outcome == "challenger":
            winner_cab, loser_cab = c_cab, t_cab
            winner_uid, loser_uid = challenger_id, target_id
        else:
            winner_cab, loser_cab = t_cab, c_cab
            winner_uid, loser_uid = target_id, challenger_id

        stake = duel.stake
        actual_stake = min(stake, loser_cab.xp)
        if actual_stake < 1:
            actual_stake = 1

        leveled, new_level = _apply_xp_to_cab(winner_cab, actual_stake)
        loser_cab.xp = max(0, loser_cab.xp - actual_stake)

        # Stats
        w_stats = dict(winner_cab.stats or {})
        l_stats = dict(loser_cab.stats or {})
        w_stats["duels_won"] = w_stats.get("duels_won", 0) + 1
        w_stats["xp_earned_total"] = w_stats.get("xp_earned_total", 0) + actual_stake
        l_stats["duels_lost"] = l_stats.get("duels_lost", 0) + 1
        winner_cab.stats = w_stats
        loser_cab.stats = l_stats

        # Quest progress for winner
        _update_quest_progress_cab(winner_cab, "win_duel")
        _update_quest_progress_cab(winner_cab, "earn_xp", actual_stake)

        # Achievements for winner
        new_achs = _check_achievements_cab(winner_cab)
        if new_achs:
            bonus = _unlock_achievements_cab(winner_cab, new_achs)
            leveled2, new_level2 = _apply_xp_to_cab(winner_cab, bonus)
            if leveled2:
                leveled = True
                new_level = new_level2

        await cabbit_repo.save(s, winner_cab)
        await cabbit_repo.save(s, loser_cab)

        return {
            "ok": True, "waiting": False, "resolved": True,
            "result": {
                "tie": False, "cancelled": False,
                "c_move": c_move, "t_move": t_move,
                "challenger_name": c_name, "target_name": t_name,
                "winner_uid": winner_uid, "loser_uid": loser_uid,
                "winner_name": winner_cab.name, "loser_name": loser_cab.name,
                "actual_stake": actual_stake,
                "leveled_up": leveled, "new_level": new_level,
                "new_achievements": new_achs if new_achs else [],
                "winner_xp": winner_cab.xp, "loser_xp": loser_cab.xp,
            },
        }
