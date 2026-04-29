from datetime import date, datetime, timedelta, timezone
import httpx
from sqlalchemy.orm import Session
from app.models import Activity, OAuthToken

STRAVA_BASE = "https://www.strava.com/api/v3"
TOKEN_URL = "https://www.strava.com/oauth/token"


def get_token(db: Session) -> OAuthToken | None:
    return db.query(OAuthToken).filter_by(provider="strava").first()


def save_token(db: Session, data: dict) -> OAuthToken:
    token = get_token(db) or OAuthToken(provider="strava")
    token.access_token = data["access_token"]
    token.refresh_token = data.get("refresh_token")
    expires_at_ts = data.get("expires_at")
    if expires_at_ts:
        token.expires_at = datetime.fromtimestamp(expires_at_ts, tz=timezone.utc)
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


def _apply_strava_zones(row: Activity, activity_id: str, headers: dict):
    """Fetch Strava HR zones for an activity and populate zone1-5_secs."""
    try:
        resp = httpx.get(f"{STRAVA_BASE}/activities/{activity_id}/zones", headers=headers)
        if resp.status_code != 200:
            return
        for block in resp.json():
            if block.get("type") != "heartrate":
                continue
            for i, z in enumerate(block.get("zones", [])[:5], start=1):
                setattr(row, f"zone{i}_secs", int(z.get("time", 0)))
    except Exception:
        pass


def sync_activities(db: Session, client_id: str, client_secret: str, days: int = 90):
    token = get_token(db)
    if not token:
        raise RuntimeError("Strava not connected — visit /auth/strava")
    _refresh_if_needed(db, token, client_id, client_secret)

    after = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    headers = {"Authorization": f"Bearer {token.access_token}"}
    page = 1

    while True:
        resp = httpx.get(
            f"{STRAVA_BASE}/athlete/activities",
            headers=headers,
            params={"after": after, "per_page": 100, "page": page},
        )
        resp.raise_for_status()
        activities = resp.json()
        if not activities:
            break

        backfill_budget = 20

        for act in activities:
            external_id = str(act["id"])
            existing = db.query(Activity).filter_by(source="strava", external_id=external_id).first()
            if existing:
                if existing.avg_hr and existing.zone1_secs is None and backfill_budget > 0:
                    _apply_strava_zones(existing, external_id, headers)
                    backfill_budget -= 1
                continue

            act_date = date.fromisoformat(act["start_date_local"][:10])
            row = Activity(
                source="strava",
                external_id=external_id,
                date=act_date,
                sport_type=act.get("sport_type") or act.get("type"),
                name=act.get("name"),
                duration_seconds=act.get("moving_time"),
                distance_meters=act.get("distance"),
                avg_hr=act.get("average_heartrate"),
                avg_watts=act.get("average_watts"),
                elevation_gain=act.get("total_elevation_gain"),
                tss=act.get("suffer_score"),
            )
            db.add(row)
            if act.get("has_heartrate"):
                _apply_strava_zones(row, external_id, headers)

        db.commit()
        page += 1
