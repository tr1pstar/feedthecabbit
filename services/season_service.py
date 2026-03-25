"""
services/season_service.py — season management service.
"""
import time

from sqlalchemy import select, delete as sql_delete

from db.engine import get_session
from db.models import Season, Cabbit, Duel, UserSkin


async def get_current_season() -> dict | None:
    """Get the current active season info."""
    async with get_session() as s:
        r = await s.execute(
            select(Season).where(Season.active == True).order_by(Season.number.desc()).limit(1)
        )
        season = r.scalar_one_or_none()
        if not season:
            return None
        return {
            "number": season.number,
            "name": season.name,
            "started_at": season.started_at,
        }


async def ensure_season(number: int = 1) -> dict:
    """Make sure at least one season row exists. Called on bot startup."""
    async with get_session() as s:
        r = await s.execute(select(Season).where(Season.active == True).limit(1))
        existing = r.scalar_one_or_none()
        if existing:
            return {"number": existing.number, "name": existing.name}

        # Create initial season
        season = Season(
            number=number,
            name=f"Сезон {number}",
            started_at=int(time.time()),
            active=True,
        )
        s.add(season)
        return {"number": number, "name": season.name}


async def start_new_season(new_number: int, name: str = "") -> dict:
    """
    Start a new season: wipe all cabbits, duels, user_skins.
    Skins catalog is preserved.
    Returns {ok, error, season_number, season_name, wiped_cabbits}
    """
    async with get_session() as s:
        # Deactivate current season
        r = await s.execute(select(Season).where(Season.active == True))
        for old in r.scalars().all():
            old.active = False

        # Check for duplicate
        existing = await s.execute(select(Season).where(Season.number == new_number))
        if existing.scalar_one_or_none():
            return {"ok": False, "error": "season_exists"}

        season_name = name or f"Сезон {new_number}"

        # Count cabbits before wipe
        count_r = await s.execute(select(Cabbit))
        wiped = len(list(count_r.scalars().all()))

        # Wipe duels
        await s.execute(sql_delete(Duel))
        # Wipe user skins (catalog preserved)
        await s.execute(sql_delete(UserSkin))
        # Wipe all cabbits
        await s.execute(sql_delete(Cabbit))

        # Create new season
        season = Season(
            number=new_number,
            name=season_name,
            started_at=int(time.time()),
            active=True,
        )
        s.add(season)

        return {
            "ok": True,
            "season_number": new_number,
            "season_name": season_name,
            "wiped_cabbits": wiped,
        }
