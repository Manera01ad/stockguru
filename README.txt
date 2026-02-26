================================================
  STOCKGURU — REAL-TIME INTELLIGENCE HUB
  Complete Setup Guide for Windows
================================================

WHAT THIS APP DOES
──────────────────
✅ Fetches live NSE/BSE stock prices every 5 minutes
✅ Fetches live Gold, Silver, Crude Oil, Crypto prices
✅ Scores your watchlist 0-100 using live momentum
✅ Shows BUY / WATCH / HOLD / AVOID signals
✅ Sends Telegram alerts when score ≥ 88 (Strong Buy)
✅ Sends 8 AM morning brief to your Telegram
✅ Sends 4 PM evening debrief to your Telegram
✅ Beautiful live dashboard at http://localhost:5000

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1 — INSTALL PYTHON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Go to: https://python.org/downloads
2. Download Python 3.11 or higher
3. During install → CHECK "Add Python to PATH"
4. Verify: Open CMD → type: python --version

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2 — GET YOUR IIFL API KEY (FREE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Go to: https://ttweb.indiainfoline.com
2. Login with your IIFL account
3. My Account → Profile → My Details
4. Click "Equity" tab
5. Trading Preferences → Trading API → Generate
6. Copy the API Key shown (valid for 6 months)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3 — CREATE TELEGRAM BOT (3 MINUTES)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Open Telegram on your phone
2. Search for: @BotFather
3. Send: /newbot
4. Give it a name: StockGuru Alerts
5. Give it username: stockguru_yourname_bot
6. BotFather gives you a TOKEN — copy it

GET YOUR CHAT ID:
7. Send any message to your new bot (search it, click Start)
8. Open this URL in browser (replace YOUR_TOKEN):
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
9. Look for "chat":{"id":XXXXXXX} — that number is your CHAT_ID

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4 — CONFIGURE YOUR .env FILE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Open the .env file with Notepad and fill in:

IIFL_API_KEY=paste_your_iifl_key_here
IIFL_SECRET_KEY=paste_your_iifl_secret_here
TELEGRAM_TOKEN=paste_your_bot_token_here
TELEGRAM_CHAT_ID=paste_your_chat_id_here

Save the file.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5 — RUN THE APP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Double-click START.bat

OR open CMD in this folder and type:
  python app.py

Then open: http://localhost:5000

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 6 — TEST TELEGRAM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Once the app is running, open:
  http://localhost:5000/api/test-telegram

You should get a message on Telegram within seconds.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TROUBLESHOOTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❌ "python is not recognized"
   → Reinstall Python with "Add to PATH" checked

❌ "pip is not recognized"
   → Run: python -m pip install flask flask-cors requests python-dotenv schedule

❌ Prices showing "--"
   → Wait 30 seconds for first fetch to complete
   → Check internet connection

❌ Telegram not working
   → Double check TOKEN and CHAT_ID in .env
   → Make sure you sent a message to the bot first

❌ Port 5000 already in use
   → Change FLASK_PORT=5001 in .env
   → Open: http://localhost:5001

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FOLDER STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
stockguru/
├── app.py              ← Main server (Flask)
├── .env                ← Your API keys (KEEP PRIVATE)
├── requirements.txt    ← Python packages
├── START.bat           ← One-click launcher
├── README.txt          ← This file
└── static/
    └── index.html      ← Dashboard UI

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DISCLAIMER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  This app is for PAPER TRADING and learning only.
    It does NOT constitute SEBI-registered investment advice.
    Never invest real money based solely on AI scores.
    Always do your own research before investing.

================================================
  Support: Ask StockGuru in Claude
================================================
