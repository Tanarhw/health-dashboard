"""
Run this locally to push your Garmin auth tokens to Railway.

Usage:
    python scripts/seed_garmin_tokens.py https://your-app.up.railway.app YOUR_SECRET_KEY
"""
import sys
import json
import base64
from pathlib import Path

def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/seed_garmin_tokens.py <railway-url> <secret-key>")
        sys.exit(1)

    base_url = sys.argv[1].rstrip("/")
    secret_key = sys.argv[2]

    # Login locally to generate garth tokens in ~/.garth
    print("Logging in to Garmin Connect locally...")
    from garminconnect import Garmin
    import garth

    email = input("Garmin email: ")
    password = input("Garmin password: ")

    client = Garmin(email, password)
    client.login()

    token_dir = Path.home() / ".garth"
    token_dir.mkdir(exist_ok=True)
    client.garth.dump(str(token_dir))
    print(f"Tokens saved to {token_dir}")

    # Read all token files and encode them
    token_files = {}
    for f in token_dir.iterdir():
        if f.is_file():
            token_files[f.name] = base64.b64encode(f.read_bytes()).decode()

    if not token_files:
        print("No token files found — login may have failed")
        sys.exit(1)

    print(f"Found token files: {list(token_files.keys())}")

    # Upload to Railway app
    import urllib.request
    payload = json.dumps({"secret": secret_key, "tokens": token_files}).encode()
    req = urllib.request.Request(
        f"{base_url}/admin/seed-garmin",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print("Upload response:", resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Upload failed ({e.code}): {e.read().decode()}")
        sys.exit(1)

    print("Done — hit Sync Now on your dashboard to pull Garmin data.")

if __name__ == "__main__":
    main()
