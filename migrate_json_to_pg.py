"""
One-time migration: JSON files -> PostgreSQL.
Usage: python migrate_json_to_pg.py [json_dir]
Default json_dir: /app/data
"""
import asyncio
import json
import os
import sys
import time

async def migrate(json_dir: str):
    from db.engine import engine, AsyncSessionLocal, init_db
    from db.models import Cabbit, Skin, UserSkin, Duel, Promo

    await init_db()
    print("Tables created.")

    async with AsyncSessionLocal() as session:
        # 1. Migrate cabbits
        cabbit_file = os.path.join(json_dir, "cabbit.json")
        cab_count = 0
        if os.path.exists(cabbit_file):
            with open(cabbit_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for uid_str, cab in data.items():
                user_id = int(uid_str)
                cabbit = Cabbit(
                    user_id=user_id,
                    name=cab.get("name", "?"),
                    xp=cab.get("xp", 0),
                    level=cab.get("level", 1),
                    coins=cab.get("coins", 0),
                    box_available=cab.get("box_available", True),
                    box_ts=cab.get("box_ts", 0),
                    last_fed=cab.get("last_fed", int(time.time())),
                    warned_12h=cab.get("warned_12h", False),
                    warned_23h=cab.get("warned_23h", False),
                    dead=cab.get("dead", False),
                    has_knife=cab.get("has_knife", False),
                    food_counts=cab.get("food_counts", {"Морковь": 0, "Корм": 0, "Вкусность": 0}),
                    duel_tokens=cab.get("duel_tokens", 0),
                    inventory=cab.get("inventory", {}),
                    sick=cab.get("sick", False),
                    sick_until=cab.get("sick_until", 0),
                    crown_boxes=cab.get("crown_boxes", 0),
                    last_raid=cab.get("last_raid", 0),
                    achievements=cab.get("achievements", []),
                    stats=cab.get("stats", {}),
                    quests=cab.get("quests", {}),
                    prestige_stars=cab.get("prestige_stars", 0),
                    skin=cab.get("skin"),
                    rules_accepted=cab.get("rules_accepted", False),
                    banned=cab.get("banned", False),
                    ban_reason=cab.get("ban_reason"),
                    last_box_day=cab.get("last_box_day"),
                    banned_by=cab.get("banned_by"),
                    banned_at=cab.get("banned_at"),
                )
                session.add(cabbit)
                # User skins
                for skin_id in cab.get("skins", []):
                    session.add(UserSkin(user_id=user_id, skin_id=skin_id))
                cab_count += 1
            print(f"Cabbits: {cab_count} migrated.")

        # 2. Migrate skins catalog
        skins_file = os.path.join(json_dir, "skins.json")
        skin_count = 0
        if os.path.exists(skins_file):
            with open(skins_file, "r", encoding="utf-8") as f:
                skins_data = json.load(f)
            for skin_id, s in skins_data.items():
                skin = Skin(
                    skin_id=skin_id,
                    file_id=s.get("file_id", ""),
                    display_name=s.get("display_name", skin_id),
                    rarity=s.get("rarity", "common"),
                    drop_chance=s.get("drop_chance", 0),
                    level_weight=s.get("level_weight", 0),
                    shop_price=s.get("shop_price"),
                    added_by=s.get("added_by", 0),
                    added_at=s.get("added_at", int(time.time())),
                )
                session.add(skin)
                skin_count += 1
            print(f"Skins: {skin_count} migrated.")

        # 3. Migrate duels
        duels_file = os.path.join(json_dir, "duels.json")
        duel_count = 0
        if os.path.exists(duels_file):
            with open(duels_file, "r", encoding="utf-8") as f:
                duels_data = json.load(f)
            for challenger_str, d in duels_data.items():
                duel = Duel(
                    challenger_id=int(challenger_str),
                    target_id=int(d.get("target", 0)),
                    stake=d.get("stake", 0),
                    round=d.get("round", 1),
                    scores=d.get("scores", {}),
                    moves=d.get("moves", {}),
                    status=d.get("status", "pending"),
                )
                session.add(duel)
                duel_count += 1
            print(f"Duels: {duel_count} migrated.")

        # 4. Migrate promos
        promos_file = os.path.join(json_dir, "promos.json")
        promo_count = 0
        if os.path.exists(promos_file):
            with open(promos_file, "r", encoding="utf-8") as f:
                promos_data = json.load(f)
            for code, p in promos_data.items():
                promo = Promo(
                    code=code,
                    promo_type=p.get("type", "морковь"),
                    uses_left=p.get("uses_left", 0),
                    used_by=p.get("used_by", []),
                    xp_amount=p.get("xp_amount", 0),
                )
                session.add(promo)
                promo_count += 1
            print(f"Promos: {promo_count} migrated.")

        await session.commit()
    
    await engine.dispose()
    print("Migration complete!")

if __name__ == "__main__":
    json_dir = sys.argv[1] if len(sys.argv) > 1 else "/app/data"
    asyncio.run(migrate(json_dir))
