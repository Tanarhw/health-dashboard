from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from app.config import settings
from app.database import SessionLocal, init_db
from app.routes import auth, dashboard
import app.sync.whoop as whoop_sync
import app.sync.garmin as garmin_sync
import app.sync.strava as strava_sync


def run_daily_sync():
    db = SessionLocal()
    try:
        if settings.whoop_client_id:
            try:
                whoop_sync.sync_cycles(db, settings.whoop_client_id, settings.whoop_client_secret)
                whoop_sync.sync_recovery(db, settings.whoop_client_id, settings.whoop_client_secret)
                whoop_sync.sync_sleep(db, settings.whoop_client_id, settings.whoop_client_secret)
            except Exception as e:
                print(f"[sync] Whoop error: {e}")

        if settings.garmin_email:
            try:
                garmin_sync.sync_daily(db, settings.garmin_email, settings.garmin_password)
                garmin_sync.sync_training_load(db, settings.garmin_email, settings.garmin_password)
                garmin_sync.sync_activities(db, settings.garmin_email, settings.garmin_password)
            except Exception as e:
                print(f"[sync] Garmin error: {e}")

        if settings.strava_client_id:
            try:
                strava_sync.sync_activities(db, settings.strava_client_id, settings.strava_client_secret)
            except Exception as e:
                print(f"[sync] Strava error: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_daily_sync, "cron", hour=4, minute=0)  # 4am daily
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Health Dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth.router)
app.include_router(dashboard.router)


@app.post("/sync/all")
def manual_sync():
    """Trigger a manual sync from the dashboard UI."""
    import threading
    threading.Thread(target=run_daily_sync, daemon=True).start()
    return {"status": "sync started"}
