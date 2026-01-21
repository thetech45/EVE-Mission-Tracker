import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import requests
import secrets
import json
import os
import time
import hashlib
import base64
import traceback
from urllib.parse import urlencode
from http.server import HTTPServer, BaseHTTPRequestHandler

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ======================
# CONFIG
# ======================
CONFIG_FILE = "config.json"
TOKEN_FILE = "token.json"
REFRESH_INTERVAL = 30  # seconds

ESI = "https://esi.evetech.net/latest"
AUTH_URL = "https://login.eveonline.com/v2/oauth/authorize"
TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"

auth_code = None
oauth_state = None
wallet_history = []  # [(timestamp, balance)]
lp_history = []      # [(timestamp, LP)]

# ======================
# LOAD CONFIG
# ======================
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

CLIENT_ID = config["client_id"]
CALLBACK_URL = config["callback_url"]
SCOPES = config["scopes"]

# ======================
# PKCE HELPERS
# ======================
def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def generate_pkce():
    verifier = b64url(secrets.token_bytes(32))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge

# ======================
# CALLBACK SERVER
# ======================
class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code, oauth_state
        if "code=" in self.path and "state=" in self.path:
            params = dict(
                p.split("=", 1)
                for p in self.path.split("?", 1)[1].split("&")
            )
            if params.get("state") != oauth_state:
                self.send_response(400)
                self.end_headers()
                return
            auth_code = params.get("code")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Login successful. You may close this window.")

# ======================
# AUTH / TOKEN CACHE WITH SAFE REFRESH
# ======================
def authenticate():
    global auth_code, oauth_state

    auth_code = None
    verifier, challenge = generate_pkce()
    oauth_state = secrets.token_urlsafe(16)

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": CALLBACK_URL,
        "scope": SCOPES,
        "state": oauth_state,
        "code_challenge": challenge,
        "code_challenge_method": "S256"
    }

    webbrowser.open(f"{AUTH_URL}?{urlencode(params)}")

    server = HTTPServer(("localhost", 8080), CallbackHandler)
    server.handle_request()

    if not auth_code:
        raise RuntimeError("OAuth login failed")

    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "client_id": CLIENT_ID,
        "code_verifier": verifier
    }

    r = requests.post(TOKEN_URL, data=data)
    r.raise_for_status()

    token = r.json()
    payload = {
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token"),
        "expires_at": time.time() + token["expires_in"]
    }

    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return payload["access_token"]

def refresh_token(refresh_token_str):
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token_str,
        "client_id": CLIENT_ID
    }
    r = requests.post(TOKEN_URL, data=data)
    r.raise_for_status()
    token_data = r.json()
    payload = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", refresh_token_str),
        "expires_at": time.time() + token_data["expires_in"]
    }
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload

def load_cached_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        token = json.load(f)

    # If expired and we have a refresh token, try to refresh
    if time.time() >= token.get("expires_at", 0):
        if "refresh_token" in token and token["refresh_token"]:
            token = refresh_token(token["refresh_token"])
        else:
            # No refresh token, force manual login
            return None

    return token.get("access_token")

# ======================
# ESI HELPERS
# ======================
def get_character_id(token):
    r = requests.get(
        "https://login.eveonline.com/oauth/verify",
        headers={"Authorization": f"Bearer {token}"}
    )
    r.raise_for_status()
    return r.json()["CharacterID"]

def get_wallet_balance(cid, token):
    r = requests.get(
        f"{ESI}/characters/{cid}/wallet/",
        headers={"Authorization": f"Bearer {token}"}
    )
    r.raise_for_status()
    return float(r.json())

def get_mission_journal(cid, token):
    r = requests.get(
        f"{ESI}/characters/{cid}/wallet/journal/",
        headers={"Authorization": f"Bearer {token}"}
    )
    r.raise_for_status()
    return r.json()

# ======================
# ISK & LP / HOUR
# ======================
def calculate_rate_per_hour(history):
    if len(history) < 2:
        return []
    rates = []
    for i in range(1, len(history)):
        t1, v1 = history[i - 1]
        t2, v2 = history[i]
        dt = (t2 - t1) / 3600
        if dt > 0:
            rates.append((v2 - v1) / dt)
    return rates

# ======================
# GUI
# ======================
class MissionTrackerApp:
    def __init__(self, root):
        self.root = root
        root.title("EVE Mission Tracker")
        root.geometry("820x650")

        self.token = load_cached_token()
        self.char_id = None

        tk.Button(root, text="Login", command=self.login).pack(pady=5)

        self.wallet_lbl = tk.Label(root, text="Wallet: —")
        self.wallet_lbl.pack()

        self.mission_lbl = tk.Label(root, text="Missions Completed: —")
        self.mission_lbl.pack()

        # Mission table
        cols = ("date", "type", "amount", "reason")
        self.tree = ttk.Treeview(root, columns=cols, show="headings", height=8)
        for c in cols:
            self.tree.heading(c, text=c.title())
        self.tree.pack(fill="x", padx=5, pady=5)

        # Buttons to show charts in pop-up windows
        tk.Button(root, text="Show ISK/hour chart", command=self.show_isk_chart).pack(pady=5)
        tk.Button(root, text="Show LP/hour chart", command=self.show_lp_chart).pack(pady=5)

        if self.token:
            self.char_id = get_character_id(self.token)
            self.refresh_loop()

    def login(self):
        try:
            self.token = authenticate()
            self.char_id = get_character_id(self.token)
            wallet_history.clear()
            lp_history.clear()
            self.refresh_loop()
            messagebox.showinfo("Success", "Logged in")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def refresh_loop(self):
        self.refresh()
        self.root.after(REFRESH_INTERVAL * 1000, self.refresh_loop)

    def refresh(self):
        if not self.token:
            return

        wallet = get_wallet_balance(self.char_id, self.token)
        now = time.time()
        wallet_history.append((now, wallet))
        wallet_history[:] = [(t, b) for t, b in wallet_history if now - t <= 3600]

        journal = get_mission_journal(self.char_id, self.token)
        missions = [j for j in journal if "mission" in j["ref_type"]]

        # Extract LP from mission entries (default 0 if not present)
        lp = sum(j.get("lp", 0) for j in missions)
        lp_history.append((now, lp))
        lp_history[:] = [(t, v) for t, v in lp_history if now - t <= 3600]

        self.wallet_lbl.config(text=f"Wallet: {wallet:,.2f} ISK")
        self.mission_lbl.config(text=f"Missions Completed: {len(missions)}")

        # Update mission table
        self.tree.delete(*self.tree.get_children())
        for j in missions[:30]:
            self.tree.insert(
                "",
                "end",
                values=(
                    j["date"],
                    j["ref_type"],
                    f'{j["amount"]:,.2f}',
                    j.get("reason", "")
                )
            )

    # ======================
    # SHOW CHARTS IN POP-UPS
    # ======================
    def show_isk_chart(self):
        win = tk.Toplevel(self.root)
        win.title("ISK / Hour Chart")
        fig, ax = plt.subplots(figsize=(6, 3))
        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.get_tk_widget().pack(fill="both", expand=True)

        isk_rates = calculate_rate_per_hour(wallet_history)
        ax.clear()
        if isk_rates:
            ax.plot(isk_rates)
            ax.set_title("ISK / Hour")
            ax.set_ylabel("ISK")
            ax.set_xlabel("Time")
        canvas.draw()

    def show_lp_chart(self):
        win = tk.Toplevel(self.root)
        win.title("LP / Hour Chart")
        fig, ax = plt.subplots(figsize=(6, 3))
        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.get_tk_widget().pack(fill="both", expand=True)

        lp_rates = calculate_rate_per_hour(lp_history)
        ax.clear()
        if lp_rates:
            ax.plot(lp_rates, color="green")
            ax.set_title("LP / Hour")
            ax.set_ylabel("LP")
            ax.set_xlabel("Time")
        canvas.draw()

# ======================
# START
# ======================
if __name__ == "__main__":
    try:
        root = tk.Tk()
        MissionTrackerApp(root)
        root.mainloop()
    except Exception:
        traceback.print_exc()
        input("Press Enter to exit...")
