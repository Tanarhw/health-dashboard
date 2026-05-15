#!/usr/bin/env python3
"""
Get Garmin OAuth tokens via real browser login (Playwright).
Bypasses the 429-blocked SSO programmatic login endpoint.

Usage:
    cd ~/health-dashboard
    .venv/bin/python scripts/garmin_browser_auth.py
"""

import base64
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs
import requests
from requests_oauthlib import OAuth1Session
from playwright.sync_api import sync_playwright

OAUTH_CONSUMER_URL = "https://thegarth.s3.amazonaws.com/oauth_consumer.json"
ANDROID_UA = "com.garmin.android.apps.connectmobile"


def get_oauth_consumer():
    resp = requests.get(OAUTH_CONSUMER_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_oauth1_token(ticket: str, consumer: dict) -> dict:
    sess = OAuth1Session(consumer["consumer_key"], consumer["consumer_secret"])
    url = (
        f"https://connectapi.garmin.com/oauth-service/oauth/"
        f"preauthorized?ticket={ticket}"
        f"&login-url=https://sso.garmin.com/sso/embed"
        f"&accepts-mfa-tokens=true"
    )
    resp = sess.get(url, headers={"User-Agent": ANDROID_UA}, timeout=15)
    resp.raise_for_status()
    parsed = parse_qs(resp.text)
    token = {k: v[0] for k, v in parsed.items()}
    token["domain"] = "garmin.com"
    return token


def exchange_oauth2(oauth1: dict, consumer: dict) -> dict:
    sess = OAuth1Session(
        consumer["consumer_key"],
        consumer["consumer_secret"],
        resource_owner_key=oauth1["oauth_token"],
        resource_owner_secret=oauth1["oauth_token_secret"],
    )
    url = "https://connectapi.garmin.com/oauth-service/oauth/exchange/user/2.0"
    data = {}
    if oauth1.get("mfa_token"):
        data["mfa_token"] = oauth1["mfa_token"]
    resp = sess.post(
        url,
        headers={
            "User-Agent": ANDROID_UA,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=data,
        timeout=15,
    )
    resp.raise_for_status()
    token = resp.json()
    token["expires_at"] = int(time.time() + token["expires_in"])
    token["refresh_token_expires_at"] = int(time.time() + token["refresh_token_expires_in"])
    return token


def browser_login() -> str:
    ticket = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        sso_url = (
            "https://sso.garmin.com/sso/embed"
            "?id=gauth-widget"
            "&embedWidget=true"
            "&gauthHost=https://sso.garmin.com/sso"
            "&clientId=GarminConnect"
            "&locale=en_US"
            "&redirectAfterAccountLoginUrl=https://sso.garmin.com/sso/embed"
            "&service=https://sso.garmin.com/sso/embed"
        )
        page.goto(sso_url)
        print()
        print("=" * 50)
        print(" Browser opened — log in with your Garmin")
        print(" credentials. The window will close")
        print(" automatically when done.")
        print("=" * 50)
        print()

        start = time.time()
        while time.time() - start < 300:
            try:
                content = page.content()
                m = re.search(r'ticket=(ST-[A-Za-z0-9\-]+)', content)
                if m:
                    ticket = m.group(1)
                    break
                url = page.url
                if "ticket=" in url:
                    m = re.search(r'ticket=(ST-[A-Za-z0-9\-]+)', url)
                    if m:
                        ticket = m.group(1)
                        break
            except Exception:
                pass
            page.wait_for_timeout(500)

        browser.close()

    if not ticket:
        print("ERROR: Timed out waiting for login. Try again.")
        raise SystemExit(1)
    return ticket


def main():
    print("Fetching OAuth consumer credentials...")
    consumer = get_oauth_consumer()

    print("Launching browser for Garmin login...")
    ticket = browser_login()

    print("Exchanging ticket for OAuth1 token...")
    oauth1 = get_oauth1_token(ticket, consumer)

    print("Exchanging OAuth1 for OAuth2 token...")
    oauth2 = exchange_oauth2(oauth1, consumer)
    print(f"  Access token: {oauth2['access_token'][:20]}...")

    print("Verifying tokens...")
    verify_resp = requests.get(
        "https://connectapi.garmin.com/userprofile-service/socialProfile",
        headers={
            "User-Agent": "GCM-iOS-5.7.2.1",
            "Authorization": f"Bearer {oauth2['access_token']}",
        },
        timeout=15,
    )
    verify_resp.raise_for_status()
    profile = verify_resp.json()
    print(f"  Authenticated as: {profile.get('displayName', 'unknown')}")

    garth_dir = Path.home() / ".garth"
    garth_dir.mkdir(exist_ok=True)
    (garth_dir / "oauth1_token.json").write_text(json.dumps(oauth1, indent=2))
    (garth_dir / "oauth2_token.json").write_text(json.dumps(oauth2, indent=2))
    print(f"\nTokens saved to {garth_dir}")
    print("Run a sync from the dashboard to pull your Garmin data.")


if __name__ == "__main__":
    main()
