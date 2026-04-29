from datetime import date, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session
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
def api_activities(weeks: int = 12, db: Session = Depends(get_db)):
    since = date.today() - timedelta(weeks=weeks)
    rows = (
        db.query(Activity)
        .filter(Activity.date >= since)
        .order_by(Activity.date)
        .all()
    )
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
