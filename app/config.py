from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    whoop_client_id: str = ""
    whoop_client_secret: str = ""
    whoop_redirect_uri: str = "http://localhost:8000/auth/whoop/callback"

    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_redirect_uri: str = "http://localhost:8000/auth/strava/callback"

    garmin_email: str = ""
    garmin_password: str = ""

    secret_key: str = "changeme"

    model_config = {"env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
