<p align="center">
  <img src="logo.svg" alt="TANAR Health Dashboard" width="420">
</p>

# TANAR Health Dashboard

A personal athletic performance dashboard that aggregates data from Whoop, Garmin, and Strava into a single dark-themed HUD. 

## Features

### Live Charts
- **Recovery & HRV** — Whoop recovery score and rMSSD HRV with 7-day rolling averages and toggleable trace visibility
- **Sleep** — Nightly total sleep hours and sleep efficiency from Whoop
- **Strain vs Next-Day Recovery** — Scatter plot showing how yesterday's training load predicts today's readiness
- **Weekly Training Volume** — Stacked bar chart by sport type across all sources; sport names normalized across Whoop/Garmin/Strava naming conventions
- **HR Zone Distribution** — Weekly time in zones 1–5 aggregated from Whoop, Garmin, and Strava activities
- **VO2 Max Trend** — Long-term VO2 max history from Garmin with 14-day rolling average
- **Acute / Chronic Load** — Garmin ATL/CTL training load ratio with danger threshold markers
- **Weekly Readiness Score** — Composite score (recovery 40%, sleep 30%, HRV 20%, load ratio 10%) trended over 12 weeks

### Stat Cards
- Recovery Score (Whoop / today)
- HRV rMSSD (Whoop / last night)
- Acute Training Load (Garmin / current)
- VO2 Max (Garmin / latest reading)
- Weekly Readiness (composite / this week)

### Other
- **Monthly Report** — Full-month summary with recovery averages, training volume by sport, and activity timeline
- **Auto Sync** — Daily background sync at 4am via APScheduler
- **Manual Sync** — "Sync Now" button triggers all sources immediately

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI + SQLAlchemy + SQLite |
| Frontend | Plotly.js + Tailwind CSS (CDN, no build step) |
| Scheduler | APScheduler (BackgroundScheduler) |
| Deploy | Railway (persistent volume at `/data/health.db`) |

## Data Sources

| Source | Auth | Data Synced |
|--------|------|-------------|
| Whoop | OAuth2 (API v2) | Recovery score, HRV, resting HR, strain, sleep, workouts + HR zones |
| Garmin | Session cookie (garminconnect + garth token cache) | Training load (ATL/CTL), Body Battery, stress, VO2 max, activities + HR zones |
| Strava | OAuth2 | Activities, distance, pace, avg HR, elevation, HR zones |

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

Edit `.env`:
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

**4. Connect accounts**
- Visit `/auth/whoop` to authorize Whoop
- Visit `/auth/strava` to authorize Strava
- Garmin authenticates automatically on first sync; tokens cached in `~/.garth`
- Hit **Sync Now** to pull your first data

## Developer Account Setup

**Whoop**
1. Go to [developer.whoop.com](https://developer.whoop.com)
2. Create an app — set redirect URI to `http://localhost:8000/auth/whoop/callback`
3. Copy Client ID and Secret to `.env`

**Strava**
1. Go to [strava.com/settings/api](https://www.strava.com/settings/api)
2. Create an app — set Authorization Callback Domain to `localhost`
3. Copy Client ID and Secret to `.env`

**Garmin**
No developer account needed. Uses your Garmin Connect email and password directly. Auth tokens are cached in `~/.garth` after first login to avoid repeated SSO hits.

## Deployment (Railway)

1. Push to GitHub
2. New Railway project → Deploy from GitHub repo
3. Add a volume mounted at `/data`
4. Add all env vars from `.env` in the Railway Variables tab
5. Update redirect URIs to your Railway domain:
   - `WHOOP_REDIRECT_URI=https://your-app.up.railway.app/auth/whoop/callback`
   - `STRAVA_REDIRECT_URI=https://your-app.up.railway.app/auth/strava/callback`
6. Re-authorize Whoop and Strava from the deployed dashboard

## Project Structure

```
app/
├── main.py           # FastAPI app, lifespan, APScheduler, /sync/all endpoint
├── config.py         # Settings loaded from .env
├── database.py       # SQLAlchemy engine, session, safe ALTER TABLE migrations
├── models.py         # ORM models: WhoopRecovery, WhoopSleep, GarminDaily,
│                     #   GarminTrainingLoad, Activity, OAuthToken
├── sync/
│   ├── whoop.py      # Whoop API v2: cycles, recovery, sleep, workouts + HR zones
│   ├── garmin.py     # Garmin: daily stats, training load, activities + HR zones
│   └── strava.py     # Strava: activities + HR zones (backfills up to 20/sync)
├── routes/
│   ├── auth.py       # OAuth2 callback handlers (Whoop, Strava)
│   └── dashboard.py  # Page routes + all JSON API endpoints
└── templates/
    ├── base.html      # HUD theme, TANAR logo, global JS (SPORT_COLORS, PLOTLY_LAYOUT)
    ├── dashboard.html # Main dashboard with all charts
    └── report.html    # Monthly summary report
```

## API Endpoints

| Endpoint | Params | Description |
|----------|--------|-------------|
| `GET /` | — | Main dashboard |
| `GET /report` | `month=YYYY-MM` | Monthly summary report |
| `POST /sync/all` | — | Trigger manual sync of all sources |
| `GET /api/recovery` | `days=60` | Whoop recovery score, HRV, resting HR, strain |
| `GET /api/sleep` | `days=60` | Whoop sleep hours, efficiency, sleep score |
| `GET /api/training-load` | `weeks=16` | Garmin ATL/CTL, load ratio, training status |
| `GET /api/activities` | `weeks=12`, `source=` | Activities from all sources (filterable by source) |
| `GET /api/garmin-daily` | `days=60` | Body Battery, stress, VO2 max |
| `GET /api/vo2max` | `days=365` | VO2 max trend (Garmin, non-null only) |
| `GET /api/hr-zones` | `weeks=12` | Weekly time in HR zones 1–5 across all activities |
| `GET /api/readiness` | `weeks=12` | Composite weekly readiness score with components |
| `GET /api/monthly-summary` | `month=YYYY-MM` | Full month aggregation by sport and metric |
