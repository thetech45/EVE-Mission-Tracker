import tkinter as tk
from tkinter import messagebox
import webbrowser
import requests
import base64
import secrets
from urllib.parse import urlencode
from http.server import HTTPServer, BaseHTTPRequestHandler

# ======================
# CONFIG – EDIT THESE
# ======================
CLIENT_ID = "2458c3ef3a084c69b521236a6ac55bf4"
CLIENT_SECRET = "eat_1ZJBUSHhBntxoK1kteZ48uTx1M1lUXrOE_1mcBM8"
CALLBACK_URL = "http://localhost:8080/callback"
SCOPES = "esi-wallet.read_character_wallet.v1"

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
    auth_bytes = auth_string.encode("utf-8")
    auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")

    headers = {
        "Authorization": f"Basic {auth_b64}"
    }

    data = {
        "grant_type": "authorization_code",
        "code": auth_code
    }

    response = requests.post(TOKEN_URL, headers=headers, data=data)
    response.raise_for_status()
    return response.json()["access_token"]

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
        self.root.geometry("420x280")

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
            messagebox.showinfo(
                "Success",
                "Authentication successful"
            )
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
# START APP
# ======================
if __name__ == "__main__":
    root = tk.Tk()
    app = MissionTrackerApp(root)
    root.mainloop()
