import base64
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models import Activity, GarminDaily, GarminTrainingLoad, WhoopRecovery, WhoopSleep

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/report", response_class=HTMLResponse)
def monthly_report(request: Request, month: str = None):
    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    return templates.TemplateResponse("report.html", {"request": request, "month": month})


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/admin/seed-garmin")
async def seed_garmin_tokens(request: Request):
    """Accept garth token files from the local seed script and write them to the persistent volume."""
    from app.sync.garmin import GARTH_TOKENS_DIR

    body = await request.json()
    if body.get("secret") != settings.secret_key:
        raise HTTPException(status_code=403, detail="Invalid secret")

    tokens: dict = body.get("tokens", {})
    if not tokens:
        raise HTTPException(status_code=400, detail="No token files provided")

    GARTH_TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    for filename, b64content in tokens.items():
        (GARTH_TOKENS_DIR / filename).write_bytes(base64.b64decode(b64content))

    return {"status": "ok", "files_written": list(tokens.keys()), "token_dir": str(GARTH_TOKENS_DIR)}


@router.get("/debug/garmin")
def debug_garmin():
    """Test Garmin connectivity and surface any auth/API errors."""
    from app.sync.garmin import _client, GARTH_TOKENS_DIR
    import traceback

    result = {
        "garmin_email_set": bool(settings.garmin_email),
        "garmin_password_set": bool(settings.garmin_password),
        "token_dir": str(GARTH_TOKENS_DIR),
        "token_dir_exists": GARTH_TOKENS_DIR.exists(),
    }

    if not settings.garmin_email or not settings.garmin_password:
        result["error"] = "GARMIN_EMAIL or GARMIN_PASSWORD not set"
        return result

    try:
        client = _client(settings.garmin_email, settings.garmin_password)
        result["login"] = "ok"
    except Exception as e:
        result["login"] = "failed"
        result["login_error"] = str(e)
        result["traceback"] = traceback.format_exc()
        return result

    try:
        today = date.today().isoformat()
        stats = client.get_stats(today)
        result["get_stats"] = "ok"
        result["stats_keys"] = list(stats.keys()) if isinstance(stats, dict) else str(type(stats))
    except Exception as e:
        result["get_stats"] = f"failed: {e}"

    try:
        raw = client.get_training_load()
        result["get_training_load"] = "ok"
        result["training_load_type"] = type(raw).__name__
        result["training_load_count"] = len(raw) if isinstance(raw, list) else "n/a"
        if isinstance(raw, list) and raw:
            result["training_load_sample_keys"] = list(raw[0].keys()) if isinstance(raw[0], dict) else str(raw[0])
    except Exception as e:
        result["get_training_load"] = f"failed: {e}"

    try:
        start = (date.today() - timedelta(days=7)).isoformat()
        acts = client.get_activities_by_date(start, date.today().isoformat())
        result["get_activities"] = "ok"
        result["activity_count_last_7d"] = len(acts) if isinstance(acts, list) else "n/a"
    except Exception as e:
        result["get_activities"] = f"failed: {e}"

    return result


# --- JSON API endpoints consumed by the frontend charts ---

@router.get("/api/recovery")
def api_recovery(days: int = 60, db: Session = Depends(get_db)):
    since = date.today() - timedelta(days=days)
    rows = (
        db.query(WhoopRecovery)
        .filter(WhoopRecovery.date >= since)
        .order_by(WhoopRecovery.date)
        .all()
    )
    return [
        {
            "date": r.date.isoformat(),
            "recovery_score": r.recovery_score,
            "hrv_rmssd": r.hrv_rmssd,
            "resting_hr": r.resting_hr,
            "strain": r.strain,
            "sleep_performance": r.sleep_performance,
        }
        for r in rows
    ]


@router.get("/api/sleep")
def api_sleep(days: int = 60, db: Session = Depends(get_db)):
    since = date.today() - timedelta(days=days)
    rows = (
        db.query(WhoopSleep)
        .filter(WhoopSleep.date >= since)
        .order_by(WhoopSleep.date)
        .all()
    )
    return [
        {
            "date": r.date.isoformat(),
            "total_sleep_hours": r.total_sleep_hours,
            "sleep_efficiency": r.sleep_efficiency,
            "sleep_score": r.sleep_score,
            "rem_hours": r.rem_hours,
            "light_hours": r.light_hours,
            "sws_hours": r.sws_hours,
            "awake_hours": r.awake_hours,
            "disturbances": r.disturbances,
        }
        for r in rows
    ]


@router.get("/api/training-load")
def api_training_load(weeks: int = 16, db: Session = Depends(get_db)):
    since = date.today() - timedelta(weeks=weeks)
    rows = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.date >= since)
        .order_by(GarminTrainingLoad.date)
        .all()
    )
    return [
        {
            "date": r.date.isoformat(),
            "acute_load": r.acute_load,
            "chronic_load": r.chronic_load,
            "load_ratio": (
                round(r.acute_load / r.chronic_load, 2)
                if r.acute_load and r.chronic_load and r.chronic_load > 0
                else None
            ),
            "training_status": r.training_status,
        }
        for r in rows
    ]


@router.get("/api/activities")
def api_activities(weeks: int = 12, source: str = None, db: Session = Depends(get_db)):
    since = date.today() - timedelta(weeks=weeks)
    q = db.query(Activity).filter(Activity.date >= since)
    if source:
        q = q.filter(Activity.source == source)
    rows = q.order_by(Activity.date).all()
    return [
        {
            "date": r.date.isoformat(),
            "source": r.source,
            "sport_type": r.sport_type,
            "name": r.name,
            "duration_minutes": round(r.duration_seconds / 60, 1) if r.duration_seconds else None,
            "distance_miles": round(r.distance_meters / 1609.344, 2) if r.distance_meters else None,
            "avg_hr": r.avg_hr,
            "avg_watts": r.avg_watts,
            "elevation_ft": round(r.elevation_gain * 3.28084) if r.elevation_gain else None,
            "tss": r.tss,
        }
        for r in rows
    ]


@router.get("/api/garmin-daily")
def api_garmin_daily(days: int = 60, db: Session = Depends(get_db)):
    since = date.today() - timedelta(days=days)
    rows = (
        db.query(GarminDaily)
        .filter(GarminDaily.date >= since)
        .order_by(GarminDaily.date)
        .all()
    )
    return [
        {
            "date": r.date.isoformat(),
            "resting_hr": r.resting_hr,
            "body_battery_end": r.body_battery_end,
            "stress_avg": r.stress_avg,
            "vo2max": r.vo2max,
        }
        for r in rows
    ]


@router.get("/api/monthly-summary")
def api_monthly_summary(month: str, db: Session = Depends(get_db)):
    year, mo = int(month[:4]), int(month[5:7])
    start = date(year, mo, 1)
    end = date(year, mo + 1, 1) if mo < 12 else date(year + 1, 1, 1)

    recovery_rows = db.query(WhoopRecovery).filter(
        WhoopRecovery.date >= start, WhoopRecovery.date < end
    ).all()

    activities = db.query(Activity).filter(
        Activity.date >= start, Activity.date < end
    ).all()

    training_rows = db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.date >= start, GarminTrainingLoad.date < end
    ).all()

    def safe_avg(vals):
        v = [x for x in vals if x is not None]
        return round(sum(v) / len(v), 1) if v else None

    return {
        "month": month,
        "recovery": {
            "avg_recovery_score": safe_avg([r.recovery_score for r in recovery_rows]),
            "avg_hrv": safe_avg([r.hrv_rmssd for r in recovery_rows]),
            "avg_resting_hr": safe_avg([r.resting_hr for r in recovery_rows]),
            "avg_strain": safe_avg([r.strain for r in recovery_rows]),
            "avg_sleep_performance": safe_avg([r.sleep_performance for r in recovery_rows]),
        },
        "training": {
            "total_activities": len(activities),
            "total_duration_hours": round(
                sum(a.duration_seconds or 0 for a in activities) / 3600, 1
            ),
            "total_distance_miles": round(
                sum(a.distance_meters or 0 for a in activities) / 1609.344, 1
            ),
            "avg_acute_load": safe_avg([r.acute_load for r in training_rows]),
            "avg_chronic_load": safe_avg([r.chronic_load for r in training_rows]),
            "by_sport": _group_by_sport(activities),
        },
    }


@router.get("/api/vo2max")
def api_vo2max(days: int = 365, db: Session = Depends(get_db)):
    since = date.today() - timedelta(days=days)
    rows = (
        db.query(GarminDaily)
        .filter(GarminDaily.date >= since, GarminDaily.vo2max.isnot(None))
        .order_by(GarminDaily.date)
        .all()
    )
    return [{"date": r.date.isoformat(), "vo2max": r.vo2max} for r in rows]


@router.get("/api/hr-zones")
def api_hr_zones(weeks: int = 12, db: Session = Depends(get_db)):
    since = date.today() - timedelta(weeks=weeks)
    activities = (
        db.query(Activity)
        .filter(Activity.date >= since, Activity.zone1_secs.isnot(None))
        .order_by(Activity.date)
        .all()
    )

    week_buckets: dict = {}
    for a in activities:
        d = a.date
        monday = d - timedelta(days=d.weekday())
        key = monday.isoformat()
        if key not in week_buckets:
            week_buckets[key] = [0, 0, 0, 0, 0]
        for i in range(5):
            week_buckets[key][i] += getattr(a, f"zone{i+1}_secs") or 0

    return [
        {
            "week": k,
            "zone1_mins": round(v[0] / 60, 1),
            "zone2_mins": round(v[1] / 60, 1),
            "zone3_mins": round(v[2] / 60, 1),
            "zone4_mins": round(v[3] / 60, 1),
            "zone5_mins": round(v[4] / 60, 1),
        }
        for k, v in sorted(week_buckets.items())
    ]


@router.get("/api/readiness")
def api_readiness(weeks: int = 12, db: Session = Depends(get_db)):
    today = date.today()

    # 30-day HRV baseline for normalization
    baseline_rows = db.query(WhoopRecovery).filter(
        WhoopRecovery.date >= today - timedelta(days=30),
        WhoopRecovery.hrv_rmssd.isnot(None),
    ).all()
    hrv_baseline = (
        sum(r.hrv_rmssd for r in baseline_rows) / len(baseline_rows)
        if baseline_rows else None
    )

    def wavg(vals):
        v = [x for x in vals if x is not None]
        return sum(v) / len(v) if v else None

    result = []
    for i in range(weeks - 1, -1, -1):
        week_end = today - timedelta(weeks=i)
        week_start = week_end - timedelta(days=6)

        rec = db.query(WhoopRecovery).filter(
            WhoopRecovery.date >= week_start, WhoopRecovery.date <= week_end
        ).all()
        slp = db.query(WhoopSleep).filter(
            WhoopSleep.date >= week_start, WhoopSleep.date <= week_end
        ).all()
        load = db.query(GarminTrainingLoad).filter(
            GarminTrainingLoad.date >= week_start, GarminTrainingLoad.date <= week_end
        ).all()

        avg_rec = wavg([r.recovery_score for r in rec])
        avg_hrv = wavg([r.hrv_rmssd for r in rec])
        avg_sleep = wavg([s.sleep_score for s in slp])

        ratios = [r.acute_load / r.chronic_load for r in load
                  if r.acute_load and r.chronic_load and r.chronic_load > 0]
        avg_ratio = wavg(ratios)

        if avg_ratio is None:    load_score = 70
        elif avg_ratio < 0.8:    load_score = 65
        elif avg_ratio <= 1.3:   load_score = 100
        elif avg_ratio <= 1.5:   load_score = 55
        else:                    load_score = 25

        hrv_score = min(100, (avg_hrv / hrv_baseline) * 100) if (avg_hrv and hrv_baseline) else avg_hrv

        components = [(avg_rec, 0.4), (avg_sleep, 0.3), (hrv_score, 0.2), (load_score, 0.1)]
        valid = [(v, w) for v, w in components if v is not None]
        total_w = sum(w for _, w in valid)
        readiness = round(sum(v * w for v, w in valid) / total_w) if valid else None

        result.append({
            "week": week_start.isoformat(),
            "readiness": readiness,
            "avg_recovery": round(avg_rec, 1) if avg_rec else None,
            "avg_hrv": round(avg_hrv, 1) if avg_hrv else None,
            "avg_sleep": round(avg_sleep, 1) if avg_sleep else None,
            "load_ratio": round(avg_ratio, 2) if avg_ratio else None,
        })

    return result


def _group_by_sport(activities: list) -> dict:
    result = {}
    for a in activities:
        sport = a.sport_type or "unknown"
        if sport not in result:
            result[sport] = {"count": 0, "distance_miles": 0, "duration_hours": 0}
        result[sport]["count"] += 1
        result[sport]["distance_miles"] += round((a.distance_meters or 0) / 1609.344, 2)
        result[sport]["duration_hours"] += round((a.duration_seconds or 0) / 3600, 2)
    return result
