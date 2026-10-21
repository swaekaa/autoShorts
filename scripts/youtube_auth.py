"""
YouTube OAuth Setup Script
==========================
Run this ONCE to authorize your YouTube channel and get the refresh token.

Usage:
    python scripts/youtube_auth.py

Prerequisites:
    1. Create OAuth 2.0 credentials in Google Cloud Console
       (Application type: Desktop app)
    2. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env
    3. Ensure the YouTube Data API v3 is enabled in your Cloud project
    4. Add your Google account as a test user if the app is in Testing mode

After running, copy the printed YOUTUBE_REFRESH_TOKEN value to your .env file.
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def main():
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        print(
            "ERROR: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env\n"
            "Get them from: https://console.cloud.google.com/apis/credentials"
        )
        sys.exit(1)

    print("=" * 60)
    print("Hindu Shorts Factory – YouTube Authorization")
    print("=" * 60)
    print(f"\nClient ID: {client_id[:20]}...")
    print("\nA browser window will open for authorization.")
    channel_id = os.getenv("YOUTUBE_CHANNEL_ID", "").strip()
    if channel_id:
        print(f"  Target channel: https://www.youtube.com/channel/{channel_id}")
    print("\nPress Enter to continue...")
    input()

    from app.youtube.oauth import YouTubeOAuth
    try:
        refresh_token = YouTubeOAuth.run_one_time_auth(
            client_id=client_id,
            client_secret=client_secret,
            port=8090,
        )
        print("\n" + "=" * 60)
        print("SUCCESS! Authorization complete.")
        print("=" * 60)
        print("\nAdd the following to your .env file:")
        print(f"\nYOUTUBE_REFRESH_TOKEN={refresh_token}")
        print("\nIMPORTANT: Keep this token secret. Do not commit it to git.")
        print("The .gitignore already excludes .env files.")

    except Exception as exc:
        print(f"\nERROR: Authorization failed: {exc}")
        print("\nTroubleshooting:")
        print("1. Ensure your OAuth app is configured correctly")
        print("2. Check that the YouTube Data API v3 is enabled")
        print("3. If in Testing mode, add your account as a test user")
        print("4. Ensure port 8090 is not in use")
        sys.exit(1)


if __name__ == "__main__":
    main()
