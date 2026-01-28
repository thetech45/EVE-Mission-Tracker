# ===================== EVE Mission Tracker =====================
# Mission tracking + ISK/hour & LP/hour charts + CSV export
# OAuth with state + refresh token support
# ===============================================================

import json
import os
import time
import threading
import webbrowser
import requests
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import matplotlib.pyplot as plt
import secrets
import csv

# ===================== FILES =====================
CONFIG_FILE = "config.json"
TOKEN_FILE = "token.json"
MISSION_STATE_FILE = "mission_state.json"

# ===================== LOAD CONFIG =====================
if not os.path.exists(CONFIG_FILE):
    raise RuntimeError("Missing config.json")

with open(CONFIG_FILE, "r") as f:
    CONFIG = json.load(f)

CLIENT_ID = CONFIG["client_id"]
CALLBACK_URL = CONFIG["callback_url"]
SCOPES = CONFIG["scopes"]

# ===================== OAUTH =====================
AUTH_URL = "https://login.eveonline.com/v2/oauth/authorize"
TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"
OAUTH_STATE = secrets.token_urlsafe(16)

# ===================== TOKEN HANDLING =====================
def save_token(token):
    with open(TOKEN_FILE, "w") as f:
        json.dump(token, f, indent=2)


def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)


def refresh_token(refresh_token):
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
    }
    r = requests.post(TOKEN_URL, data=data)
    r.raise_for_status()
    token = r.json()
    save_token(token)
    return token


# ===================== CHARACTER INFO =====================
def get_character_id(access_token):
    r = requests.get(
        "https://login.eveonline.com/oauth/verify",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    r.raise_for_status()
    return r.json()["CharacterID"]


# ===================== MISSION STATE =====================
def load_mission_state():
    if not os.path.exists(MISSION_STATE_FILE):
        return {"last_journal_id": None, "missions_completed": 0}
    with open(MISSION_STATE_FILE, "r") as f:
        return json.load(f)


def save_mission_state(state):
    with open(MISSION_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ===================== ESI CALLS =====================
def fetch_wallet(char_id, token):
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    r = requests.get(f"https://esi.evetech.net/latest/characters/{char_id}/wallet/", headers=headers)
    r.raise_for_status()
    return r.json()


def fetch_wallet_journal(char_id, token):
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    r = requests.get(f"https://esi.evetech.net/latest/characters/{char_id}/wallet/journal/", headers=headers)
    r.raise_for_status()
    return r.json()


def fetch_loyalty_points(char_id, token):
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    r = requests.get(f"https://esi.evetech.net/latest/characters/{char_id}/loyalty/points/", headers=headers)
    r.raise_for_status()
    data = r.json()
    return sum(entry.get("loyalty_points", 0) for entry in data)


# ===================== MISSION DETECTION =====================
def process_new_missions(journal):
    state = load_mission_state()
    last_id = state["last_journal_id"]
    new_missions = 0

    for entry in journal:
        jid = entry["id"]
        if last_id and jid <= last_id:
            break
        if entry.get("ref_type") == "agent_mission_reward":
            new_missions += 1

    if journal:
        state["last_journal_id"] = journal[0]["id"]

    state["missions_completed"] += new_missions
    save_mission_state(state)
    return state["missions_completed"], new_missions


# ===================== GUI =====================
class MissionTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("EVE Mission Tracker")
        self.token = load_token()
        self.char_id = None

        self.mission_total = tk.StringVar(value="0")
        self.session_missions = tk.StringVar(value="0")

        self.time_history = []
        self.isk_history = []
        self.lp_history = []

        ttk.Button(root, text="Login", command=self.login).pack(pady=5)
        ttk.Label(root, text="Total Missions Completed:").pack()
        ttk.Label(root, textvariable=self.mission_total, font=("Arial", 14)).pack()
        ttk.Label(root, text="Missions This Session:").pack()
        ttk.Label(root, textvariable=self.session_missions).pack()

        ttk.Button(root, text="Show ISK / Hour Chart", command=self.show_isk_chart).pack(pady=4)
        ttk.Button(root, text="Show LP / Hour Chart", command=self.show_lp_chart).pack(pady=4)
        ttk.Button(root, text="Export CSV", command=self.export_csv).pack(pady=4)

        self.session_count = 0

        if self.token:
            self.initialize()

    def login(self):
        params = {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": CALLBACK_URL,
            "scope": SCOPES,
            "state": OAUTH_STATE,
        }
        url = AUTH_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
        webbrowser.open(url)
        threading.Thread(target=self.start_server, daemon=True).start()

    def start_server(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self_inner):
                query = parse_qs(urlparse(self_inner.path).query)
                code = query.get("code")
                returned_state = query.get("state")

                if not code or not returned_state or returned_state[0] != OAUTH_STATE:
                    self_inner.send_response(400)
                    self_inner.end_headers()
                    self_inner.wfile.write(b"Invalid OAuth state.")
                    return

                data = {
                    "grant_type": "authorization_code",
                    "code": code[0],
                    "client_id": CLIENT_ID,
                    "redirect_uri": CALLBACK_URL,
                }
                r = requests.post(TOKEN_URL, data=data)
                r.raise_for_status()
                token = r.json()
                save_token(token)
                self.token = token

                self_inner.send_response(200)
                self_inner.end_headers()
                self_inner.wfile.write(b"Login successful. You may close this window.")
                self.initialize()

        HTTPServer(("localhost", 8080), Handler).serve_forever()

    def initialize(self):
        if "refresh_token" in self.token:
            self.token = refresh_token(self.token["refresh_token"])
        self.char_id = get_character_id(self.token["access_token"])
        self.update_loop()

    def update_loop(self):
        try:
            wallet = fetch_wallet(self.char_id, self.token)
            lp = fetch_loyalty_points(self.char_id, self.token)
            journal = fetch_wallet_journal(self.char_id, self.token)

            total, new = process_new_missions(journal)
            self.mission_total.set(str(total))
            self.session_count += new
            self.session_missions.set(str(self.session_count))

            now = time.time()
            self.time_history.append(now)
            self.isk_history.append(wallet)
            self.lp_history.append(lp)

        except Exception as e:
            print("Update error:", e)

        self.root.after(30000, self.update_loop)

    def show_isk_chart(self):
        if len(self.time_history) < 2:
            messagebox.showinfo("Not enough data", "Let the tracker run longer.")
            return
        rates = [
            (self.isk_history[i] - self.isk_history[i - 1]) / ((self.time_history[i] - self.time_history[i - 1]) / 3600)
            for i in range(1, len(self.isk_history))
        ]
        plt.figure()
        plt.plot(rates)
        plt.title("ISK / Hour")
        plt.ylabel("ISK/hour")
        plt.xlabel("Sample")
        plt.show()

    def show_lp_chart(self):
        if len(self.time_history) < 2:
            messagebox.showinfo("Not enough data", "Let the tracker run longer.")
            return
        rates = [
            (self.lp_history[i] - self.lp_history[i - 1]) / ((self.time_history[i] - self.time_history[i - 1]) / 3600)
            for i in range(1, len(self.lp_history))
        ]
        plt.figure()
        plt.plot(rates)
        plt.title("LP / Hour")
        plt.ylabel("LP/hour")
        plt.xlabel("Sample")
        plt.show()

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv")
        if not path:
            return
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "wallet_isk", "total_lp"])
            for t, isk, lp in zip(self.time_history, self.isk_history, self.lp_history):
                writer.writerow([datetime.fromtimestamp(t), isk, lp])
        messagebox.showinfo("Export complete", "CSV file saved.")


# ===================== MAIN =====================
if __name__ == "__main__":
    root = tk.Tk()
    MissionTrackerApp(root)
    root.mainloop()



