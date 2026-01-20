import tkinter as tk
from tkinter import messagebox
import webbrowser
import requests
import base64
import secrets
import json
import os
import traceback
from urllib.parse import urlencode
from http.server import HTTPServer, BaseHTTPRequestHandler

# ======================
# LOAD CONFIG.JSON
# ======================
CONFIG_FILE = "config.json"

if not os.path.exists(CONFIG_FILE):
    raise RuntimeError(
        "config.json not found. Please create it before running the program."
    )

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

REQUIRED_KEYS = ["client_id", "client_secret", "callback_url", "scopes"]
for key in REQUIRED_KEYS:
    if not config.get(key):
        raise RuntimeError(f"Missing '{key}' in config.json")

CLIENT_ID = config["client_id"]
CLIENT_SECRET = config["client_secret"]
CALLBACK_URL = config["callback_url"]
SCOPES = config["scopes"]

# ======================
# CONSTANTS
# ======================
ESI = "https://esi.evetech.net/latest"
AUTH_URL = "https://login.eveonline.com/v2/oauth/authorize"
TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"

auth_code = None
oauth_state = None

# ======================
# OAUTH CALLBACK SERVER
# ======================
class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code, oauth_state

        if "code=" in self.path and "state=" in self.path:
            query = self.path.split("?", 1)[1]
            params = dict(p.split("=", 1) for p in query.split("&"))

            if params.get("state") != oauth_state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid OAuth state.")
                return

            auth_code = params.get("code")

            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                b"Authentication successful. You may close this window."
            )

# ======================
# AUTH FUNCTION
# ======================
def authenticate():
    global auth_code, oauth_state

    auth_code = None
    oauth_state = secrets.token_urlsafe(16)

    params = {
        "response_type": "code",
        "redirect_uri": CALLBACK_URL,
        "client_id": CLIENT_ID,
        "scope": SCOPES,
        "state": oauth_state
    }

    webbrowser.open(f"{AUTH_URL}?{urlencode(params)}")

    server = HTTPServer(("localhost", 8080), CallbackHandler)
    server.handle_request()

    auth_string = f"{CLIENT_ID}:{CLIENT_SECRET}"
    auth_b64 = base64.b64encode(auth_string.encode()).decode()

    headers = {"Authorization": f"Basic {auth_b64}"}
    data = {
        "grant_type": "authorization_code",
        "code": auth_code
    }

    r = requests.post(TOKEN_URL, headers=headers, data=data)
    r.raise_for_status()
    return r.json()["access_token"]

# ======================
# ESI HELPERS
# ======================
def get_character_id(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        "https://login.eveonline.com/oauth/verify",
        headers=headers
    )
    r.raise_for_status()
    return r.json()["CharacterID"]

def get_wallet_balance(char_id, token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        f"{ESI}/characters/{char_id}/wallet/",
        headers=headers
    )
    r.raise_for_status()
    return float(r.json())

def get_mission_stats(char_id, token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        f"{ESI}/characters/{char_id}/wallet/journal/",
        headers=headers
    )
    r.raise_for_status()

    missions = 0
    total_isk = 0.0

    for entry in r.json():
        if entry.get("ref_type") in (
            "mission_reward",
            "mission_bonus",
            "agent_mission_reward"
        ):
            missions += 1
            total_isk += float(entry.get("amount", 0))

    return missions, total_isk

# ======================
# GUI APP
# ======================
class MissionTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("EVE Mission Tracker")
        self.root.geometry("420x300")

        self.token = None
        self.char_id = None

        tk.Button(
            root,
            text="Login with EVE Online",
            command=self.login
        ).pack(pady=10)

        self.wallet_label = tk.Label(root, text="Wallet Balance: —")
        self.wallet_label.pack(pady=5)

        self.missions_label = tk.Label(root, text="Missions Completed: —")
        self.missions_label.pack(pady=5)

        self.earned_label = tk.Label(root, text="Mission ISK Earned: —")
        self.earned_label.pack(pady=5)

        tk.Button(
            root,
            text="Refresh",
            command=self.refresh
        ).pack(pady=10)

    def login(self):
        try:
            self.token = authenticate()
            self.char_id = get_character_id(self.token)
            self.refresh()
            messagebox.showinfo("Success", "Authentication successful")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def refresh(self):
        if not self.token:
            return

        wallet = get_wallet_balance(self.char_id, self.token)
        missions, isk = get_mission_stats(self.char_id, self.token)

        self.wallet_label.config(
            text=f"Wallet Balance: {wallet:,.2f} ISK"
        )
        self.missions_label.config(
            text=f"Missions Completed: {missions}"
        )
        self.earned_label.config(
            text=f"Mission ISK Earned: {isk:,.2f}"
        )

# ======================
# SAFE STARTUP
# ======================
if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = MissionTrackerApp(root)
        root.mainloop()
    except Exception:
        traceback.print_exc()
        input("Press Enter to exit...")

