DON'T MESS WITH THE CONFIG FILE. IF YOU DO IT WILL BREAK THE MAIN PROGRAM.








Requirements:
  Latest version of Python https://www.python.org/downloads/
  pip also needs to be installed https://www.youtube.com/watch?v=CWbT-E7f73w



📘 EVE Online Mission Tracker – User Guide
🛰️ What This Program Does

The EVE Mission Tracker is a desktop application that connects to EVE Online using CCP’s ESI system and helps you track:

💰 Wallet balance (ISK)

📜 Mission-related wallet activity

🔢 How many missions you’ve completed

📊 ISK per hour

📊 LP per hour

🔐 Secure login that only needs to be done once

After the first login, the program remembers you and does not require re-authentication.

🧰 Requirements
✅ What you need installed

Windows 10 or 11

Python 3.10 or newer

An EVE Online account

An ESI Application from CCP

🐍 Step 1: Install Python

Go to: https://www.python.org/downloads/

Download the latest Python 3

IMPORTANT:
✔ Check “Add Python to PATH” during installation

Finish installation

Verify Python is installed

Open Command Prompt and run:

python --version


You should see something like:

Python 3.12.x

📦 Step 2: Install Required Python Packages

Open Command Prompt in the folder where Mission.py is located and run:

pip install requests matplotlib

🔑 Step 3: Create an EVE ESI Application

Go to: https://developers.eveonline.com/

Log in with your EVE account

Click Create New Application

Set:

Name: Mission Tracker

Connection Type: Authentication & API Access

Callback URL:

http://localhost:8080/


Save the app

Copy your Client ID

⚙️ Step 4: Create config.json

In the same folder as Mission.py, create a file named:

config.json


Paste this inside (replace YOUR_CLIENT_ID):

{
  "client_id": "YOUR_CLIENT_ID",
  "callback_url": "http://localhost:8080/",
  "scopes": "esi-wallet.read_character_wallet.v1"
}


📌 Important

No client secret is required

This uses PKCE, which is safe for desktop apps

▶️ Step 5: Run the Program

In Command Prompt, run:

python Mission.py


The GUI window will open.

🔐 Step 6: First Login (One-Time)

Click Login

Your web browser opens

Log into EVE

Approve access

You’ll see “Login successful”

Close the browser tab

📁 The program will now create:

token.json


This file:

Stores your login token

Automatically refreshes

Prevents future logins

➡️ You will NOT need to log in again


  






ISK Donations to: Theodore Natinde
