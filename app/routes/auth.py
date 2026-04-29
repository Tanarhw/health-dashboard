import secrets
import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.sync.whoop import save_token as whoop_save_token
from app.sync.strava import save_token as strava_save_token

router = APIRouter(prefix="/auth")

WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"


@router.get("/whoop")
def whoop_login():
    state = secrets.token_hex(16)
    params = (
        f"?response_type=code"
        f"&client_id={settings.whoop_client_id}"
        f"&redirect_uri={settings.whoop_redirect_uri}"
        f"&scope=read:recovery read:sleep read:workout read:cycles read:body_measurement offline"
        f"&state={state}"
    )
    return RedirectResponse(WHOOP_AUTH_URL + params)


@router.get("/whoop/callback")
def whoop_callback(
    request: Request,
    code: str = None,
    error: str = None,
    state: str = None,
    db: Session = Depends(get_db),
):
    if error or not code:
        return HTMLResponse(f"<h2>Whoop auth failed</h2><p>Error: {error}</p><p>Full URL: {request.url}</p>")
    resp = httpx.post(WHOOP_TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.whoop_redirect_uri,
        "client_id": settings.whoop_client_id,
        "client_secret": settings.whoop_client_secret,
    })
    resp.raise_for_status()
    whoop_save_token(db, resp.json())
    return RedirectResponse("/?connected=whoop")


@router.get("/strava")
def strava_login():
    params = (
        f"?client_id={settings.strava_client_id}"
        f"&redirect_uri={settings.strava_redirect_uri}"
        f"&response_type=code"
        f"&scope=activity:read_all"
    )
    return RedirectResponse(STRAVA_AUTH_URL + params)


@router.get("/strava/callback")
def strava_callback(
    request: Request,
    code: str = None,
    error: str = None,
    db: Session = Depends(get_db),
):
    if error or not code:
        return HTMLResponse(f"<h2>Strava auth failed</h2><p>Error: {error}</p><p>Full URL: {request.url}</p>")
    resp = httpx.post(STRAVA_TOKEN_URL, data={
        "client_id": settings.strava_client_id,
        "client_secret": settings.strava_client_secret,
        "code": code,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    strava_save_token(db, resp.json())
    return RedirectResponse("/?connected=strava")
