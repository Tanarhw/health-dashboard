from datetime import date, datetime, timedelta, timezone
import httpx
from sqlalchemy.orm import Session
from app.models import OAuthToken, WhoopRecovery, WhoopSleep

WHOOP_BASE = "https://api.prod.whoop.com/developer/v2"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"


def get_token(db: Session) -> OAuthToken | None:
    return db.query(OAuthToken).filter_by(provider="whoop").first()


def save_token(db: Session, data: dict) -> OAuthToken:
    token = get_token(db) or OAuthToken(provider="whoop")
    token.access_token = data["access_token"]
    token.refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in", 3600)
    token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    db.merge(token)
    db.commit()
    return token


def _refresh_if_needed(db: Session, token: OAuthToken, client_id: str, client_secret: str):
    if token.expires_at and datetime.now(timezone.utc) >= token.expires_at.replace(tzinfo=timezone.utc):
        resp = httpx.post(TOKEN_URL, data={
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        })
        resp.raise_for_status()
        save_token(db, resp.json())


def _headers(token: OAuthToken) -> dict:
    return {"Authorization": f"Bearer {token.access_token}"}


def _paginate(url: str, headers: dict, start: str):
    next_token = None
    while True:
        params = {"start": start, "limit": 25}
        if next_token:
            params["nextToken"] = next_token
        resp = httpx.get(url, headers=headers, params=params)
        resp.raise_for_status()
        body = resp.json()
        yield from body.get("records", [])
        next_token = body.get("next_token")
        if not next_token:
            break


def sync_cycles(db: Session, client_id: str, client_secret: str, days: int = 90):
    token = get_token(db)
    if not token:
        raise RuntimeError("Whoop not connected — visit /auth/whoop")
    _refresh_if_needed(db, token, client_id, client_secret)

    start = (date.today() - timedelta(days=days)).isoformat() + "T00:00:00.000Z"

    for cycle in _paginate(f"{WHOOP_BASE}/cycle", _headers(token), start):
        cycle_id = cycle["id"]
        cycle_date = date.fromisoformat(cycle["start"][:10])
        score = cycle.get("score") or {}

        existing = db.query(WhoopRecovery).filter_by(cycle_id=cycle_id).first()
        if existing:
            existing.strain = score.get("strain")
        else:
            db.add(WhoopRecovery(
                cycle_id=cycle_id,
                date=cycle_date,
                strain=score.get("strain"),
            ))

    db.commit()


def sync_recovery(db: Session, client_id: str, client_secret: str, days: int = 90):
    token = get_token(db)
    if not token:
        raise RuntimeError("Whoop not connected — visit /auth/whoop")
    _refresh_if_needed(db, token, client_id, client_secret)

    start = (date.today() - timedelta(days=days)).isoformat() + "T00:00:00.000Z"

    for rec in _paginate(f"{WHOOP_BASE}/recovery", _headers(token), start):
        cycle_id = rec["cycle_id"]
        score = rec.get("score") or {}

        row = db.query(WhoopRecovery).filter_by(cycle_id=cycle_id).first()
        if not row:
            continue
        row.recovery_score = score.get("recovery_score")
        row.hrv_rmssd = score.get("hrv_rmssd_milli")
        row.resting_hr = score.get("resting_heart_rate")

    db.commit()


def sync_sleep(db: Session, client_id: str, client_secret: str, days: int = 90):
    token = get_token(db)
    if not token:
        raise RuntimeError("Whoop not connected — visit /auth/whoop")
    _refresh_if_needed(db, token, client_id, client_secret)

    start = (date.today() - timedelta(days=days)).isoformat() + "T00:00:00.000Z"

    for sleep in _paginate(f"{WHOOP_BASE}/activity/sleep", _headers(token), start):
        if sleep.get("nap"):
            continue  # skip naps
        sleep_id = sleep["id"]
        sleep_date = date.fromisoformat(sleep["start"][:10])
        score = sleep.get("score") or {}
        stage = score.get("stage_summary") or {}

        existing = db.query(WhoopSleep).filter_by(sleep_id=sleep_id).first()
        if not existing:
            db.add(WhoopSleep(
                sleep_id=sleep_id,
                date=sleep_date,
                total_sleep_hours=round(stage.get("total_in_bed_time_milli", 0) / 3_600_000, 2),
                sleep_efficiency=score.get("sleep_efficiency_percentage"),
                sleep_score=score.get("sleep_performance_percentage"),
            ))

    db.commit()
