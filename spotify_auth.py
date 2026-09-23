"""
Run this ONCE to authenticate Spotify.
After this, BLAZE handles Spotify automatically forever.

Usage:
    py -3.11 spotify_auth.py
"""

import os
from dotenv import load_dotenv
load_dotenv()

CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
REDIRECT_URI  = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
CACHE_PATH    = os.path.join(os.path.expanduser("~"), ".blaze_spotify_cache")

if not CLIENT_ID or not CLIENT_SECRET:
    print("ERROR: SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET not found in .env")
    exit(1)

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth

    print("Opening browser for Spotify login...")
    print("After logging in, you'll be redirected to a blank page — that's normal.")
    print("Copy the full URL from your browser and paste it here.\n")

    auth = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope="user-read-playback-state user-modify-playback-state user-read-currently-playing",
        cache_path=CACHE_PATH,
        open_browser=True
    )

    sp = spotipy.Spotify(auth_manager=auth)
    user = sp.current_user()
    print(f"\n✅ Spotify authenticated successfully!")
    print(f"   Account: {user['display_name']} ({user['email']})")
    print(f"   Plan: {user['product'].upper()}")
    print(f"   Token saved to: {CACHE_PATH}")
    print(f"\nYou can now run BLAZE normally. Spotify will work automatically.")

except ImportError:
    print("spotipy not installed. Run: py -3.11 -m pip install spotipy")
except Exception as e:
    print(f"Auth failed: {e}")
