"""
core/game_math.py — pure game logic, NO DB, NO Telegram.
"""
import random
import time
from core.constants import (FOOD_TABLE, KNIFE_CHANCE, ITEM_TABLE, RANDOM_EVENTS,
    EVOLUTIONS, REELS, ACHIEVEMENTS, QUEST_POOL, BEATS, SICKNESS_DURATION,
    DEATH_24H, WARN_12H, WARN_23H, SKIN_LEVEL_INTERVAL)


def xp_for_level(level: int) -> int:
    return int(100 * (level ** 1.6))


def get_evolution(level: int) -> dict:
    result = EVOLUTIONS[0]
    for evo in EVOLUTIONS:
        if level >= evo["min_level"]:
            result = evo
    return result


def get_box_interval(level: int) -> int:
    return get_evolution(level)["box_cd"]


def roll_item() -> tuple[str, str] | None:
    r = random.random() * 100
    cum = 0
    for name, emoji, chance in ITEM_TABLE:
        cum += chance
        if r < cum:
            return name, emoji
    return None


def roll_event() -> dict | None:
    for ev in RANDOM_EVENTS:
        if random.random() * 100 < ev["chance"]:
            return ev
    return None


def roll_box(knife_exists: bool) -> tuple[str, str, int, bool]:
    knife_roll = random.random() * 100 < KNIFE_CHANCE
    if knife_roll and not knife_exists:
        return "Нож", "🔪", 0, True
    r = random.randint(1, 100)
    cum = 0
    for name, emoji, chance, xp in FOOD_TABLE:
        cum += chance
        if r <= cum:
            return name, emoji, xp, False
    return FOOD_TABLE[0][0], FOOD_TABLE[0][1], FOOD_TABLE[0][3], False


def check_sickness(sick: bool, sick_until: int) -> bool:
    if not sick:
        return False
    return int(time.time()) < sick_until


def apply_xp(xp: int, level: int, amount: int) -> tuple[int, int, bool]:
    """Returns (new_xp, new_level, leveled_up)."""
    xp += amount
    leveled_up = False
    while xp >= xp_for_level(level):
        xp -= xp_for_level(level)
        level += 1
        leveled_up = True
    return xp, level, leveled_up


def do_prestige(prestige_stars: int) -> tuple[int, dict]:
    stars = prestige_stars + 1
    reset = {
        "prestige_stars": stars, "level": 1, "xp": 0,
        "food_counts": {"Морковь": 0, "Корм": 0, "Вкусность": 0},
        "last_fed": int(time.time()),
        "warned_12h": False, "warned_23h": False,
        "sick": False, "sick_until": 0, "crown_boxes": 0,
    }
    return stars, reset


def spin_slots() -> tuple[list[str], float]:
    result = [random.choice(REELS) for _ in range(3)]
    if result[0] == result[1] == result[2]:
        if result[0] == "💎": return result, 15.0
        if result[0] == "7️⃣": return result, 10.0
        return result, 5.0
    if result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        return result, 2.0
    return result, 0.0


def roll_skin_drop(droppable: list[tuple[str, dict]], owned: list[str]) -> tuple[str, dict] | None:
    for skin_id, skin in droppable:
        if skin_id in owned:
            continue
        if random.random() * 100 < skin.get("drop_chance", 0):
            return skin_id, skin
    return None


def roll_skin_level(pool: list[tuple[str, dict]], owned: list[str]) -> tuple[str, dict] | None:
    available = [(sid, s) for sid, s in pool if sid not in owned]
    if not available:
        return None
    weights = [s.get("level_weight", 1) for _, s in available]
    return random.choices(available, weights=weights, k=1)[0]


def check_achievements(stats: dict, earned: set, level: int) -> list[dict]:
    stats["max_level"] = max(stats.get("max_level", 0), level)
    new = []
    for ach in ACHIEVEMENTS:
        if ach["id"] not in earned and stats.get(ach["stat"], 0) >= ach["need"]:
            new.append(ach)
    return new


def unlock_achievements(earned_list: list, new_achs: list[dict]) -> int:
    total_xp = 0
    for ach in new_achs:
        earned_list.append(ach["id"])
        total_xp += ach["reward"]
    return total_xp


def generate_quests() -> list[dict]:
    from datetime import datetime
    pool = random.sample(QUEST_POOL, min(3, len(QUEST_POOL)))
    quests = []
    for q in pool:
        idx = random.randrange(len(q["targets"]))
        quests.append({
            "id": q["id"], "desc": q["desc"].format(n=q["targets"][idx]),
            "target": q["targets"][idx], "progress": 0,
            "reward": q["rewards"][idx], "claimed": False,
        })
    return quests


def get_or_refresh_quests(quest_data: dict) -> tuple[list[dict], bool]:
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    if quest_data.get("date") != today:
        tasks = generate_quests()
        return tasks, True
    return quest_data.get("tasks", []), False


def update_quest_progress(tasks: list[dict], action: str, amount: int = 1):
    for t in tasks:
        if t["id"] == action and not t["claimed"]:
            t["progress"] = min(t["progress"] + amount, t["target"])


def resolve_duel_move(c_move: str, t_move: str) -> str:
    if c_move == t_move:
        return "tie"
    if BEATS[c_move] == t_move:
        return "challenger"
    return "target"


def hunger_percent(last_fed: int) -> int:
    elapsed = int(time.time()) - last_fed
    return max(0, 100 - int(elapsed / DEATH_24H * 100))
