from sqlalchemy import BigInteger, Boolean, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Season(Base):
    __tablename__ = "seasons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    number: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    started_at: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Cabbit(Base):
    __tablename__ = "cabbits"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(20))
    xp: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    coins: Mapped[int] = mapped_column(Integer, default=0)
    box_available: Mapped[bool] = mapped_column(Boolean, default=True)
    box_ts: Mapped[int] = mapped_column(Integer, default=0)
    last_fed: Mapped[int] = mapped_column(Integer)
    warned_12h: Mapped[bool] = mapped_column(Boolean, default=False)
    warned_23h: Mapped[bool] = mapped_column(Boolean, default=False)
    dead: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    has_knife: Mapped[bool] = mapped_column(Boolean, default=False)
    food_counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    duel_tokens: Mapped[int] = mapped_column(Integer, default=0)
    inventory: Mapped[dict] = mapped_column(JSONB, default=dict)
    sick: Mapped[bool] = mapped_column(Boolean, default=False)
    sick_until: Mapped[int] = mapped_column(Integer, default=0)
    crown_boxes: Mapped[int] = mapped_column(Integer, default=0)
    last_raid: Mapped[int] = mapped_column(Integer, default=0)
    achievements: Mapped[list] = mapped_column(JSONB, default=list)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    quests: Mapped[dict] = mapped_column(JSONB, default=dict)
    prestige_stars: Mapped[int] = mapped_column(Integer, default=0)
    skin: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rules_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    ban_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_box_day: Mapped[str | None] = mapped_column(String(10), nullable=True)
    banned_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    banned_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    season: Mapped[int] = mapped_column(Integer, default=1)

class Skin(Base):
    __tablename__ = "skins"
    skin_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    file_id: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(64))
    rarity: Mapped[str] = mapped_column(String(16), default="common")
    drop_chance: Mapped[float] = mapped_column(Float, default=0)
    level_weight: Mapped[int] = mapped_column(Integer, default=0)
    shop_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    added_by: Mapped[int] = mapped_column(BigInteger, default=0)
    added_at: Mapped[int] = mapped_column(Integer, default=0)

class UserSkin(Base):
    __tablename__ = "user_skins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    skin_id: Mapped[str] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("user_id", "skin_id"),)

class Duel(Base):
    __tablename__ = "duels"
    challenger_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_id: Mapped[int] = mapped_column(BigInteger, index=True)
    stake: Mapped[int] = mapped_column(Integer)
    round: Mapped[int] = mapped_column(Integer, default=1)
    scores: Mapped[dict] = mapped_column(JSONB, default=dict)
    moves: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[int] = mapped_column(Integer, default=0)

class Promo(Base):
    __tablename__ = "promos"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    promo_type: Mapped[str] = mapped_column(String(16))
    uses_left: Mapped[int] = mapped_column(Integer, default=1)
    used_by: Mapped[list] = mapped_column(JSONB, default=list)
    xp_amount: Mapped[int] = mapped_column(Integer, default=0)
