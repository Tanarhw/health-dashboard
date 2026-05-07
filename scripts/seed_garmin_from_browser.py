"""
Use this when the normal seed script fails with 429 (Garmin SSO rate limit).
It seeds Railway with a bearer token extracted from your browser session.

Steps:
  1. Open https://connect.garmin.com in Chrome or Firefox and log in.
  2. Press F12 to open DevTools.
  3. Go to the Network tab.
  4. Click on any activity or page in Garmin Connect to trigger API calls.
  5. In the Network tab, click on any request to connectapi.garmin.com.
  6. Open the "Headers" panel and find the "Authorization" request header.
  7. Copy everything after "Bearer " (it's a long string starting with "eyJ").
  8. Run:
       python scripts/seed_garmin_from_browser.py <railway-url> <secret-key> <token>

The token typically lasts ~1 hour. Run this script again with a fresh token
if Garmin stops syncing.
"""
import sys
import json
import base64
import urllib.request
import urllib.error


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)

    base_url   = sys.argv[1].rstrip("/")
    secret_key = sys.argv[2]
    bearer     = sys.argv[3].strip()

    if not bearer.startswith("eyJ"):
        print("That doesn't look like a JWT — it should start with 'eyJ'.")
        print("Make sure you copied just the token part, not the 'Bearer ' prefix.")
        sys.exit(1)

    # Construct a minimal garth-compatible oauth2_token.json.
    # Without a refresh token the session lasts ~1 hour, after which you
    # re-run this script with a fresh browser token.
    oauth2 = {
        "scope": "CONNECT_READ CONNECT_WRITE",
        "jti": "browser-seeded",
        "token_type": "Bearer",
        "access_token": bearer,
        "refresh_token": "",
        "expires_in": 3600,
        "refresh_token_expires_in": 0,
    }

    token_files = {
        "oauth2_token.json": base64.b64encode(
            json.dumps(oauth2).encode()
        ).decode()
    }

    print("Uploading token to Railway...")
    payload = json.dumps({"secret": secret_key, "tokens": token_files}).encode()
    req = urllib.request.Request(
        f"{base_url}/admin/seed-garmin",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print("Response:", resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Upload failed ({e.code}): {e.read().decode()}")
        sys.exit(1)

    print("\nDone. Hit Sync Now on your dashboard — Garmin data should start populating.")
    print("Note: this token expires in ~1 hour. Re-run with a fresh browser token if needed.")


if __name__ == "__main__":
    main()
