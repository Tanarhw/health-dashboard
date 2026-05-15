from datetime import date, timedelta
from pathlib import Path
from sqlalchemy.orm import Session
from app.models import Activity, GarminDaily, GarminTrainingLoad

# Use persistent volume on Railway if available, otherwise ~/.garth
_DATA_DIR = Path("/data")
GARTH_TOKENS_DIR = _DATA_DIR / ".garth" if _DATA_DIR.exists() else Path.home() / ".garth"


def _client(email: str, password: str):
    from garminconnect import Garmin
    import garth

    if GARTH_TOKENS_DIR.exists() and any(GARTH_TOKENS_DIR.iterdir()):
        try:
            garth.resume(str(GARTH_TOKENS_DIR))
            client = Garmin(email, password)
            client.garth = garth.client
            # Populate display_name needed for user-specific API URLs
            client.display_name = garth.client.profile.get("displayName") or garth.client.profile.get("userName")
            return client
        except Exception as e:
            print(f"[garmin] Cached token load failed ({e}), trying fresh login")

    import sys
    if not sys.stdin.isatty():
        raise RuntimeError(
            "No Garmin tokens cached. Run scripts/garmin_browser_auth.py to authenticate."
        )

    print("[garmin] Performing fresh Garmin login")
    client = Garmin(email, password)
    client.login()
    GARTH_TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    client.garth.dump(str(GARTH_TOKENS_DIR))
    return client


def sync_daily(db: Session, email: str, password: str, days: int = 90):
    print("[garmin] sync_daily starting")
    try:
        client = _client(email, password)
    except Exception as e:
        print(f"[garmin] sync_daily auth failed: {e}")
        return

    today = date.today()
    added = 0

    for i in range(days):
        d = today - timedelta(days=i)
        if db.query(GarminDaily).filter_by(date=d).first():
            continue
        try:
            stats = client.get_stats(d.isoformat())
        except Exception as e:
            print(f"[garmin] get_stats({d}) failed: {e}")
            continue

        db.add(GarminDaily(
            date=d,
            resting_hr=stats.get("restingHeartRate"),
            body_battery_end=stats.get("bodyBatteryMostRecentValue"),
            stress_avg=stats.get("averageStressLevel"),
            steps=stats.get("totalSteps"),
            vo2max=stats.get("vo2MaxValue"),
        ))
        added += 1

    db.commit()
    print(f"[garmin] sync_daily done — {added} new rows")


def sync_training_load(db: Session, email: str, password: str):
    print("[garmin] sync_training_load starting")
    try:
        client = _client(email, password)
    except Exception as e:
        print(f"[garmin] sync_training_load auth failed: {e}")
        return

    added = 0
    for i in range(16 * 7):
        d = date.today() - timedelta(days=i)
        if db.query(GarminTrainingLoad).filter_by(date=d).first():
            continue
        try:
            raw = client.get_training_status(d.isoformat())
        except Exception as e:
            print(f"[garmin] get_training_status({d}) failed: {e}")
            continue

        # Response is a dict; training load lives under mostRecentTrainingStatus
        status_data = raw.get("mostRecentTrainingStatus", {}).get("latestTrainingStatusData", {})
        entry = next(iter(status_data.values()), {}) if status_data else {}
        atl_dto = entry.get("acuteTrainingLoadDTO") or {}

        acute = atl_dto.get("dailyTrainingLoadAcute")
        chronic = atl_dto.get("dailyTrainingLoadChronic")
        status = entry.get("trainingStatusFeedbackPhrase") or entry.get("trainingStatus")

        db.add(GarminTrainingLoad(date=d, acute_load=acute, chronic_load=chronic, training_status=str(status) if status else None))

        # Backfill vo2max onto the daily row if missing
        vo2 = raw.get("mostRecentVO2Max", {}).get("generic", {}).get("vo2MaxPreciseValue")
        if vo2:
            daily_row = db.query(GarminDaily).filter_by(date=d).first()
            if daily_row and daily_row.vo2max is None:
                daily_row.vo2max = vo2

        added += 1

    db.commit()
    print(f"[garmin] sync_training_load done — {added} new rows")


def _apply_garmin_zones(client, row: Activity, activity_id: str):
    try:
        zones = client.get_activity_hr_in_timezones(activity_id)
        for z in zones:
            n = z.get("zoneNumber") or 0
            s = int(z.get("secsInZone") or 0)
            if 1 <= n <= 5:
                setattr(row, f"zone{n}_secs", s)
    except Exception:
        pass


def sync_activities(db: Session, email: str, password: str, days: int = 90):
    print("[garmin] sync_activities starting")
    try:
        client = _client(email, password)
    except Exception as e:
        print(f"[garmin] sync_activities auth failed: {e}")
        return

    start = date.today() - timedelta(days=days)
    try:
        raw = client.get_activities_by_date(start.isoformat(), date.today().isoformat())
        print(f"[garmin] fetched {len(raw)} activities")
    except Exception as e:
        print(f"[garmin] get_activities_by_date failed: {e}")
        return

    backfill_budget = 30
    added = 0

    for act in raw:
        external_id = str(act.get("activityId", ""))
        if not external_id:
            continue

        existing = db.query(Activity).filter_by(source="garmin", external_id=external_id).first()
        if existing:
            if existing.avg_hr and existing.zone1_secs is None and backfill_budget > 0:
                _apply_garmin_zones(client, existing, external_id)
                backfill_budget -= 1
            continue

        act_date_str = (act.get("startTimeLocal") or "")[:10]
        try:
            act_date = date.fromisoformat(act_date_str)
        except ValueError:
            continue

        row = Activity(
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
        )
        db.add(row)
        added += 1
        if act.get("averageHR"):
            _apply_garmin_zones(client, row, external_id)

    db.commit()
    print(f"[garmin] sync_activities done — {added} new rows")
