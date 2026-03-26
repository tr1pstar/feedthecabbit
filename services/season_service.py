"""
services/season_service.py — season management service.
"""
import time

from sqlalchemy import select, delete as sql_delete

from db.engine import get_session
from db.models import Season, Cabbit, Duel, UserSkin, SeasonTop


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

        # Remove old season with same number if exists
        existing = await s.execute(select(Season).where(Season.number == new_number))
        old_dup = existing.scalar_one_or_none()
        if old_dup:
            await s.delete(old_dup)
            await s.flush()

        season_name = name or f"Сезон {new_number}"

        # Save top 3 of current season
        r_current = await s.execute(select(Season).where(Season.active == False).order_by(Season.number.desc()).limit(1))
        old_season = r_current.scalar_one_or_none()
        old_number = old_season.number if old_season else 0

        top_r = await s.execute(
            select(Cabbit).where(Cabbit.dead == False)
            .order_by(Cabbit.prestige_stars.desc(), Cabbit.level.desc(), Cabbit.xp.desc())
            .limit(3)
        )
        for place, cab in enumerate(top_r.scalars().all(), 1):
            s.add(SeasonTop(
                season_number=old_number,
                place=place,
                name=cab.name,
                level=cab.level,
                xp=cab.xp,
                prestige_stars=cab.prestige_stars,
            ))

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


async def get_past_seasons() -> list[dict]:
    """Get list of past seasons that have top records."""
    async with get_session() as s:
        r = await s.execute(
            select(Season).where(Season.active == False)
            .order_by(Season.number.desc()).limit(3)
        )
        seasons = []
        for season in r.scalars().all():
            seasons.append({
                "number": season.number,
                "name": season.name,
            })
        return seasons


async def get_season_top(season_number: int) -> list[dict]:
    """Get top 3 for a specific past season."""
    async with get_session() as s:
        r = await s.execute(
            select(SeasonTop).where(SeasonTop.season_number == season_number)
            .order_by(SeasonTop.place)
        )
        return [
            {
                "place": t.place,
                "name": t.name,
                "level": t.level,
                "xp": t.xp,
                "prestige_stars": t.prestige_stars,
            }
            for t in r.scalars().all()
        ]
