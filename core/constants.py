"""
core/constants.py — all game constants extracted from original modules.
"""

# ─── Cabbit core ──────────────────────────────────────────────────────────────

BOX_INTERVAL    = 30 * 60
WARN_12H        = 12 * 3600
WARN_23H        = 23 * 3600
DEATH_24H       = 24 * 3600
NAMING_STATE    = 1
KNIFE_CHANCE    = 0.15

FOOD_TABLE = [
    ("Морковь",   "🥕", 60,  80),
    ("Корм",      "🍗", 20,  200),
    ("Вкусность", "✨", 20,  500),
]

FOOD_HEAL = {
    "Морковь":   3 * 3600,
    "Корм":      6 * 3600,
    "Вкусность": 12 * 3600,
}

EVOLUTIONS = [
    {"name": "Малыш",      "emoji": "🐣", "min_level": 1,  "xp_mult": 1.0, "box_cd": 30 * 60},
    {"name": "Подросток",   "emoji": "🐰", "min_level": 5,  "xp_mult": 1.2, "box_cd": 30 * 60},
    {"name": "Воин",        "emoji": "⚔️",  "min_level": 15, "xp_mult": 1.5, "box_cd": 30 * 60},
    {"name": "Легенда",     "emoji": "👑", "min_level": 30, "xp_mult": 2.0, "box_cd": 30 * 60},
]

RANDOM_EVENTS = [
    {"text": "🎁 Кеббит нашёл клад!",            "xp": 300,  "chance": 5},
    {"text": "💫 Кеббит поскользнулся!",          "xp": -50,  "chance": 10},
    {"text": "🐦 Подружился с птичкой!",           "tokens": 1, "chance": 8},
    {"text": "🌀 Портал! Телепорт +1 уровень!",   "level_up": True, "chance": 2},
    {"text": "💎 Нашёл алмаз!",                   "xp": 500,  "chance": 3},
    {"text": "🌧 Дождь, кеббит грустит",          "xp": -30,  "chance": 8},
    {"text": "🍀 Четырёхлистный клевер!",          "xp": 150,  "chance": 7},
]

ITEM_TABLE = [
    ("Щит",      "🛡", 0.15),
    ("Зелье",    "🧪", 2),
    ("Магнит",   "🧲", 1.5),
    ("Корона",   "👑", 1.5),
    ("Таблетка", "💊", 3),
]

SICKNESS_CHANCE   = 5
SICKNESS_DURATION = 6 * 3600
RAID_COOLDOWN     = 2 * 3600

RULES_TEXT = (
    "📜 <b>Правила игры «Кеббит»</b>\n\n"
    "1. 🚫 <b>Запрещены мультиаккаунты.</b>\n"
    "   Один человек — один кеббит. Использование нескольких аккаунтов "
    "для получения преимуществ приведёт к бану кеббита.\n\n"
    "2. 🐛 <b>Запрещён багоюз.</b>\n"
    "   Использование багов в своих целях запрещено. "
    "Нашёл баг? Нажми 📬 Обратная связь и сообщи о нём. "
    "За найденные баги выдаётся вознаграждение!\n\n"
    "Нажми <b>✅ Принимаю</b> чтобы продолжить."
)

REPLY_KB_LABELS = {"🐰 Кеббит", "🎰 Казино", "⚔️ Бой", "📋 Квесты", "🏪 Магазин", "📊 Топ", "📖 Вики", "📬 Обратная связь"}

# ─── Pagination ───────────────────────────────────────────────────────────────

DUEL_PAGE_SIZE      = 5
CABBITLIST_PAGE_SIZE = 10

# ─── Skins & economy ─────────────────────────────────────────────────────────

SKIN_LEVEL_INTERVAL = 5
COINS_PER_BOX       = (5, 30)
COINS_DAILY_BONUS   = 50
COINS_RAID_OK       = 15
RENAME_COST         = 500

RARITY_EMOJI = {
    "common":    "⚪",
    "rare":      "🔵",
    "epic":      "🟣",
    "legendary": "🟡",
}

RARITY_ORDER = {
    "common":    0,
    "rare":      1,
    "epic":      2,
    "legendary": 3,
}

# Capsule shop: rarity → price in coins
CAPSULE_PRICES = {
    "common":    250,
    "rare":      500,
    "epic":      800,
    "legendary": 1250,
}

CAPSULE_NAMES = {
    "common":    "Обычная капсула",
    "rare":      "Редкая капсула",
    "epic":      "Эпическая капсула",
    "legendary": "Легендарная капсула",
}

CABBIT_PHOTO = "/app/cabbit.jpg"

# ─── Casino ───────────────────────────────────────────────────────────────────

REELS = ["🍒", "🍋", "🔔", "💎", "7️⃣", "🍀"]

# ─── Duel ─────────────────────────────────────────────────────────────────────

DUEL_ACCEPT_TIMEOUT = 60  # seconds — auto-cancel if not accepted

BEATS = {"камень": "ножницы", "ножницы": "бумага", "бумага": "камень"}
EMOJI = {"камень": "✊", "ножницы": "✌️", "бумага": "🖐"}

# ─── Quests ───────────────────────────────────────────────────────────────────

QUEST_POOL = [
    {"id": "open_boxes",  "desc": "Открой {n} коробок",       "targets": [2, 3, 5],  "rewards": [100, 200, 350]},
    {"id": "win_duel",    "desc": "Выиграй дуэль",            "targets": [1],         "rewards": [250]},
    {"id": "use_casino",  "desc": "Сыграй {n} раз в казино",  "targets": [2, 3, 5],   "rewards": [100, 150, 250]},
    {"id": "do_raid",     "desc": "Проведи {n} рейдов",       "targets": [1, 2],      "rewards": [150, 250]},
    {"id": "earn_xp",     "desc": "Заработай {n} XP",         "targets": [200, 500],  "rewards": [100, 200]},
    {"id": "feed_cabbit", "desc": "Покорми кеббита {n} раз",  "targets": [3, 5],      "rewards": [150, 300]},
]

# ─── Achievements ─────────────────────────────────────────────────────────────

ACHIEVEMENTS = [
    {"id": "first_box",  "name": "Первая коробка",  "emoji": "📦", "desc": "Открой первую коробку",       "stat": "boxes_opened",    "need": 1,     "reward": 50},
    {"id": "boxes_10",   "name": "Коллекционер",    "emoji": "📦", "desc": "Открой 10 коробок",            "stat": "boxes_opened",    "need": 10,    "reward": 100},
    {"id": "boxes_50",   "name": "Охотник за едой", "emoji": "🍽",  "desc": "Открой 50 коробок",            "stat": "boxes_opened",    "need": 50,    "reward": 300},
    {"id": "boxes_100",  "name": "Обжора",          "emoji": "🎁", "desc": "Открой 100 коробок",           "stat": "boxes_opened",    "need": 100,   "reward": 500},
    {"id": "level_5",    "name": "Подросток",       "emoji": "🌱", "desc": "Достигни 5 уровня",            "stat": "max_level",       "need": 5,     "reward": 200},
    {"id": "level_15",   "name": "Воин",            "emoji": "⚔️",  "desc": "Достигни 15 уровня",           "stat": "max_level",       "need": 15,    "reward": 500},
    {"id": "level_30",   "name": "Легенда",         "emoji": "👑", "desc": "Достигни 30 уровня",           "stat": "max_level",       "need": 30,    "reward": 1000},
    {"id": "duel_win",   "name": "Дуэлянт",        "emoji": "🥊", "desc": "Выиграй первую дуэль",         "stat": "duels_won",       "need": 1,     "reward": 100},
    {"id": "duel_10",    "name": "Чемпион",         "emoji": "🏆", "desc": "Выиграй 10 дуэлей",            "stat": "duels_won",       "need": 10,    "reward": 500},
    {"id": "kill_1",     "name": "Убийца",          "emoji": "🔪", "desc": "Убей кеббита",                 "stat": "kills",           "need": 1,     "reward": 200},
    {"id": "raid_1",     "name": "Налётчик",        "emoji": "💰", "desc": "Успешный рейд",                "stat": "raids_ok",        "need": 1,     "reward": 100},
    {"id": "raid_10",    "name": "Грабитель",       "emoji": "🦹", "desc": "10 успешных рейдов",            "stat": "raids_ok",        "need": 10,    "reward": 400},
    {"id": "casino_win", "name": "Везунчик",        "emoji": "🎰", "desc": "Выиграй в казино",             "stat": "casino_wins",     "need": 1,     "reward": 100},
    {"id": "casino_10",  "name": "Картёжник",       "emoji": "🃏", "desc": "Выиграй 10 раз в казино",       "stat": "casino_wins",     "need": 10,    "reward": 300},
    {"id": "xp_1000",    "name": "Тысячник",        "emoji": "💫", "desc": "Заработай 1000 XP суммарно",    "stat": "xp_earned_total", "need": 1000,  "reward": 200},
    {"id": "xp_10000",   "name": "Магнат",          "emoji": "💎", "desc": "Заработай 10000 XP суммарно",   "stat": "xp_earned_total", "need": 10000, "reward": 1000},
    {"id": "xp_50000",   "name": "Олигарх",         "emoji": "🏦", "desc": "Заработай 50000 XP суммарно",   "stat": "xp_earned_total", "need": 50000, "reward": 3000},
    # Коробки
    {"id": "boxes_250",  "name": "Фанат коробок",   "emoji": "📬", "desc": "Открой 250 коробок",           "stat": "boxes_opened",    "need": 250,   "reward": 800},
    {"id": "boxes_500",  "name": "Маньяк коробок",  "emoji": "🗃", "desc": "Открой 500 коробок",            "stat": "boxes_opened",    "need": 500,   "reward": 1500},
    # Дуэли
    {"id": "duel_3",     "name": "Боец",             "emoji": "🥋", "desc": "Выиграй 3 дуэли",              "stat": "duels_won",       "need": 3,     "reward": 200},
    {"id": "duel_25",    "name": "Гладиатор",        "emoji": "🗡", "desc": "Выиграй 25 дуэлей",             "stat": "duels_won",       "need": 25,    "reward": 1000},
    {"id": "duel_50",    "name": "Непобедимый",      "emoji": "🛡", "desc": "Выиграй 50 дуэлей",             "stat": "duels_won",       "need": 50,    "reward": 2000},
    # Рейды
    {"id": "raid_25",    "name": "Пират",            "emoji": "🏴‍☠️", "desc": "25 успешных рейдов",            "stat": "raids_ok",        "need": 25,    "reward": 800},
    {"id": "raid_50",    "name": "Легенда рейдов",   "emoji": "⚓", "desc": "50 успешных рейдов",             "stat": "raids_ok",        "need": 50,    "reward": 1500},
    # Казино
    {"id": "casino_25",  "name": "Азартный",         "emoji": "🎲", "desc": "Выиграй 25 раз в казино",       "stat": "casino_wins",     "need": 25,    "reward": 600},
    {"id": "casino_50",  "name": "Шулер",            "emoji": "🃏", "desc": "Выиграй 50 раз в казино",       "stat": "casino_wins",     "need": 50,    "reward": 1200},
    {"id": "casino_lose_10", "name": "Неудачник",    "emoji": "😭", "desc": "Проиграй 10 раз в казино",      "stat": "casino_losses",   "need": 10,    "reward": 150},
    {"id": "casino_lose_50", "name": "Донатер казино","emoji": "🤡", "desc": "Проиграй 50 раз в казино",     "stat": "casino_losses",   "need": 50,    "reward": 500},
    # Убийства
    {"id": "kill_3",     "name": "Серийный убийца",  "emoji": "☠️",  "desc": "Убей 3 кеббитов",              "stat": "kills",           "need": 3,     "reward": 500},
    {"id": "kill_5",     "name": "Жнец",             "emoji": "💀", "desc": "Убей 5 кеббитов",               "stat": "kills",           "need": 5,     "reward": 1000},
    # Престиж
    {"id": "prestige_1", "name": "Перерождение",     "emoji": "🌟", "desc": "Сделай первый престиж",         "stat": "prestige_count",  "need": 1,     "reward": 500},
    {"id": "prestige_3", "name": "Феникс",           "emoji": "🔥", "desc": "Сделай 3 престижа",             "stat": "prestige_count",  "need": 3,     "reward": 1500},
]

# ─── Promo types ──────────────────────────────────────────────────────────────

PROMO_TYPES = {
    "морковь":   {"emoji": "🥕", "food": "Морковь",   "xp": 80},
    "корм":      {"emoji": "🍗", "food": "Корм",       "xp": 200},
    "вкусность": {"emoji": "✨", "food": "Вкусность",  "xp": 500},
    "жетон":     {"emoji": "🥊", "food": None,         "xp": 0},
    "xp":        {"emoji": "💰", "food": None,         "xp": 0},
}

# ─── Reaction mini-game ──────────────────────────────────────────────────────

MIN_INTERVAL = 3600
MAX_INTERVAL = 3 * 3600
TIMEOUT      = 300
BIG_REWARD   = (200, 500)
SMALL_REWARD = 50
