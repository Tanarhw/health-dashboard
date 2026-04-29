from datetime import date, timedelta
from pathlib import Path
from sqlalchemy.orm import Session
from app.models import Activity, GarminDaily, GarminTrainingLoad

GARTH_TOKENS_DIR = Path.home() / ".garth"


def _client(email: str, password: str):
    from garminconnect import Garmin
    import garth

    # Use cached tokens if available — avoids repeated SSO hits
    if GARTH_TOKENS_DIR.exists():
        try:
            garth.resume(str(GARTH_TOKENS_DIR))
            client = Garmin(email, password)
            client.garth = garth.client
            return client
        except Exception:
            pass  # tokens stale, fall through to fresh login

    client = Garmin(email, password)
    client.login()
    GARTH_TOKENS_DIR.mkdir(exist_ok=True)
    client.garth.dump(str(GARTH_TOKENS_DIR))
    return client


def sync_daily(db: Session, email: str, password: str, days: int = 90):
    client = _client(email, password)
    today = date.today()

    for i in range(days):
        d = today - timedelta(days=i)
        existing = db.query(GarminDaily).filter_by(date=d).first()
        if existing:
            continue
        try:
            stats = client.get_stats(d.isoformat())
        except Exception:
            continue

        db.add(GarminDaily(
            date=d,
            resting_hr=stats.get("restingHeartRate"),
            body_battery_end=stats.get("bodyBatteryMostRecentValue"),
            stress_avg=stats.get("averageStressLevel"),
            steps=stats.get("totalSteps"),
            vo2max=stats.get("vo2MaxValue"),
        ))

    db.commit()


def sync_training_load(db: Session, email: str, password: str):
    client = _client(email, password)

    try:
        raw = client.get_training_load()
    except Exception:
        return

    for entry in raw if isinstance(raw, list) else []:
        try:
            d = date.fromisoformat(entry.get("calendarDate", "")[:10])
        except ValueError:
            continue

        existing = db.query(GarminTrainingLoad).filter_by(date=d).first()
        if existing:
            continue

        db.add(GarminTrainingLoad(
            date=d,
            acute_load=entry.get("acuteLoad"),
            chronic_load=entry.get("chronicLoad"),
            training_status=entry.get("trainingStatus"),
        ))

    db.commit()


def sync_activities(db: Session, email: str, password: str, days: int = 90):
    client = _client(email, password)
    start = date.today() - timedelta(days=days)

    try:
        raw = client.get_activities_by_date(start.isoformat(), date.today().isoformat())
    except Exception:
        return

    for act in raw:
        external_id = str(act.get("activityId", ""))
        if not external_id:
            continue

        existing = db.query(Activity).filter_by(source="garmin", external_id=external_id).first()
        if existing:
            continue

        act_date_str = (act.get("startTimeLocal") or "")[:10]
        try:
            act_date = date.fromisoformat(act_date_str)
        except ValueError:
            continue

        db.add(Activity(
            source="garmin",
            external_id=external_id,
            date=act_date,
            sport_type=act.get("activityType", {}).get("typeKey"),
            name=act.get("activityName"),
            duration_seconds=int(act.get("duration") or 0),
            distance_meters=act.get("distance"),
            avg_hr=act.get("averageHR"),
            avg_watts=act.get("avgPower"),
            elevation_gain=act.get("elevationGain"),
        ))

    db.commit()
