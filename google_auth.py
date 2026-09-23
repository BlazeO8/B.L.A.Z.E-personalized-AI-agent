"""
Run this ONCE to connect BLAZE to all your Google services:
Calendar, Gmail, Drive, Tasks, and Sheets.

Setup steps BEFORE running this:
1. Go to https://console.cloud.google.com/
2. Create a new project (or use existing)
3. Enable these APIs (search each, click Enable):
   - Google Calendar API
   - Gmail API
   - Google Drive API
   - Tasks API
   - Google Sheets API
4. Go to "Credentials" -> "Create Credentials" -> "OAuth client ID"
5. Application type: "Desktop app"
6. Copy the Client ID and Client Secret

7. Configure OAuth consent screen -> Add yourself as a test user
   (required since the app isn't published/verified)

8. Add to your .env file:
   GOOGLE_CLIENT_ID=your_client_id
   GOOGLE_CLIENT_SECRET=your_client_secret

Usage:
    py -3.11 google_auth.py
"""

import os
from dotenv import load_dotenv
load_dotenv()

CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8765/callback")
TOKEN_PATH    = os.path.join(os.path.expanduser("~"), ".blaze_google_token.json")

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/contacts.readonly",
]

if not CLIENT_ID or not CLIENT_SECRET:
    print("ERROR: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET not found in .env")
    print("\nSetup steps:")
    print("1. Go to https://console.cloud.google.com/")
    print("2. Create a project, enable: Calendar API, Gmail API, Drive API, Tasks API, Sheets API")
    print("3. Credentials -> Create Credentials -> OAuth client ID -> Desktop app")
    print("4. OAuth consent screen -> add yourself as a Test User")
    print("5. Copy Client ID and Secret into your .env file")
    exit(1)

try:
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_config = {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uris": [REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    print("Opening browser for Google login...")
    print("Log in and grant access to Calendar, Gmail, Drive, Tasks, and Sheets.\n")
    print("NOTE: You'll see an 'unverified app' warning since this is your")
    print("personal app — click 'Advanced' -> 'Go to BLAZE (unsafe)' to proceed.\n")

    flow  = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=8765)

    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())

    print(f"\n✅ All Google services connected successfully!")
    print(f"   Token saved to: {TOKEN_PATH}")
    print(f"\nBLAZE can now use:")
    print(f"   • Calendar — schedule meetings with auto Google Meet links")
    print(f"   • Gmail — read, search, and send emails")
    print(f"   • Drive — search and open files")
    print(f"   • Tasks — voice-controlled to-do list")
    print(f"   • Sheets — log expenses/entries automatically")

except ImportError:
    print("Required packages not installed. Run:")
    print("py -3.11 -m pip install google-auth-oauthlib google-api-python-client")
except Exception as e:
    print(f"Auth failed: {e}")
