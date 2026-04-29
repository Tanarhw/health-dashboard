# Health Dashboard

A personal health metrics dashboard that aggregates data from Whoop, Garmin, and Strava into one place. Generates daily charts and monthly reports covering training load, recovery trends, sleep, and activity progression.

## Features

- **Recovery & HRV** — Whoop recovery score, HRV (rMSSD), resting heart rate, sleep performance
- **Training Load** — Garmin acute/chronic load (ATL/CTL), training status, Body Battery, VO2max
- **Activity Volume** — Weekly volume by sport type from Strava, with pace and duration trends
- **Sleep** — Nightly sleep hours and efficiency from Whoop
- **Monthly Report** — Dedicated summary view with sport breakdown, recovery averages, and activity timeline
- **Auto Sync** — Daily background sync at 4am, plus manual "Sync Now" button in the dashboard

## Stack

- **Backend** — FastAPI + SQLAlchemy + SQLite
- **Frontend** — Plotly.js + Tailwind CSS (no build step)
- **Scheduler** — APScheduler for daily background sync
- **Deploy** — Railway

## Data Sources

| Source | Auth | Data |
|--------|------|------|
| Whoop | OAuth2 (API v2) | Recovery score, HRV, strain, sleep |
| Garmin | Session (garminconnect) | Training load, Body Battery, VO2max, activities |
| Strava | OAuth2 | Activities, distance, pace, heart rate |

## Local Setup

**1. Clone and install**
```bash
git clone https://github.com/Tanarhw/health-dashboard.git
cd health-dashboard
pip install -r requirements.txt
```

**2. Configure credentials**
```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Whoop — developer.whoop.com
WHOOP_CLIENT_ID=
WHOOP_CLIENT_SECRET=
WHOOP_REDIRECT_URI=http://localhost:8000/auth/whoop/callback

# Strava — strava.com/settings/api
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=
STRAVA_REDIRECT_URI=http://localhost:8000/auth/strava/callback

# Garmin Connect (no dev account needed)
GARMIN_EMAIL=
GARMIN_PASSWORD=

SECRET_KEY=any-random-string
```

**3. Run**
```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000

**4. Connect your accounts**

- Visit http://localhost:8000/auth/whoop to authorize Whoop
- Visit http://localhost:8000/auth/strava to authorize Strava
- Garmin connects automatically on first sync using your credentials
- Hit **Sync Now** in the dashboard header to pull your data

## Developer Account Setup

**Whoop**
1. Go to [developer.whoop.com](https://developer.whoop.com)
2. Create an app, set redirect URI to `http://localhost:8000/auth/whoop/callback`
3. Copy Client ID and Secret to `.env`

**Strava**
1. Go to [strava.com/settings/api](https://www.strava.com/settings/api)
2. Create an app, set Authorization Callback Domain to `localhost`
3. Copy Client ID and Secret to `.env`

**Garmin**
No developer account needed — uses your Garmin Connect email and password directly. Auth tokens are cached in `~/.garth` after first login.

## Deployment (Railway)

1. Push to GitHub
2. Create a new Railway project → Deploy from GitHub repo
3. Add all env vars from `.env` in the Railway Variables tab
4. Update redirect URIs to your Railway domain:
   - `WHOOP_REDIRECT_URI=https://your-app.up.railway.app/auth/whoop/callback`
   - `STRAVA_REDIRECT_URI=https://your-app.up.railway.app/auth/strava/callback`
5. Re-authorize Whoop and Strava from the deployed dashboard

## Project Structure

```
app/
├── main.py          # FastAPI app, lifespan, scheduler, manual sync endpoint
├── config.py        # Settings from .env
├── database.py      # SQLAlchemy engine + session
├── models.py        # ORM models (WhoopRecovery, WhoopSleep, GarminDaily, Activity, ...)
├── sync/
│   ├── whoop.py     # Whoop API v2 client (cycles, recovery, sleep)
│   ├── garmin.py    # Garmin sync via garminconnect
│   └── strava.py    # Strava API client
├── routes/
│   ├── auth.py      # OAuth2 callback handlers
│   └── dashboard.py # Dashboard + report pages, JSON API endpoints
└── templates/
    ├── base.html
    ├── dashboard.html
    └── report.html
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Main dashboard |
| `GET /report?month=YYYY-MM` | Monthly summary report |
| `POST /sync/all` | Trigger manual sync |
| `GET /api/recovery?days=60` | Recovery + HRV data |
| `GET /api/sleep?days=60` | Sleep data |
| `GET /api/training-load?weeks=16` | Garmin training load |
| `GET /api/activities?weeks=12` | All activities |
| `GET /api/garmin-daily?days=60` | Body Battery, stress, VO2max |
| `GET /api/monthly-summary?month=YYYY-MM` | Monthly aggregated stats |
