from datetime import date, datetime
from sqlalchemy import Date, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String, unique=True)  # "whoop" | "strava"
    access_token: Mapped[str] = mapped_column(String)
    refresh_token: Mapped[str] = mapped_column(String, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class WhoopRecovery(Base):
    __tablename__ = "whoop_recovery"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(Integer, unique=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    recovery_score: Mapped[float] = mapped_column(Float, nullable=True)
    hrv_rmssd: Mapped[float] = mapped_column(Float, nullable=True)
    resting_hr: Mapped[float] = mapped_column(Float, nullable=True)
    sleep_performance: Mapped[float] = mapped_column(Float, nullable=True)
    strain: Mapped[float] = mapped_column(Float, nullable=True)


class WhoopSleep(Base):
    __tablename__ = "whoop_sleep"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sleep_id: Mapped[int] = mapped_column(Integer, unique=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    total_sleep_hours: Mapped[float] = mapped_column(Float, nullable=True)
    sleep_efficiency: Mapped[float] = mapped_column(Float, nullable=True)
    sleep_score: Mapped[float] = mapped_column(Float, nullable=True)


class GarminDaily(Base):
    __tablename__ = "garmin_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    resting_hr: Mapped[float] = mapped_column(Float, nullable=True)
    body_battery_end: Mapped[float] = mapped_column(Float, nullable=True)
    stress_avg: Mapped[float] = mapped_column(Float, nullable=True)
    steps: Mapped[int] = mapped_column(Integer, nullable=True)
    vo2max: Mapped[float] = mapped_column(Float, nullable=True)


class GarminTrainingLoad(Base):
    __tablename__ = "garmin_training_load"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    acute_load: Mapped[float] = mapped_column(Float, nullable=True)
    chronic_load: Mapped[float] = mapped_column(Float, nullable=True)
    training_status: Mapped[str] = mapped_column(String, nullable=True)


class Activity(Base):
    """Unified activity table — deduped by source + external_id."""
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String)       # "garmin" | "strava"
    external_id: Mapped[str] = mapped_column(String)
    date: Mapped[date] = mapped_column(Date, index=True)
    sport_type: Mapped[str] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=True)
    distance_meters: Mapped[float] = mapped_column(Float, nullable=True)
    avg_hr: Mapped[float] = mapped_column(Float, nullable=True)
    avg_watts: Mapped[float] = mapped_column(Float, nullable=True)
    elevation_gain: Mapped[float] = mapped_column(Float, nullable=True)
    tss: Mapped[float] = mapped_column(Float, nullable=True)  # training stress score
