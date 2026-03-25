# Runbook: StockGuru Flask Server Startup & Troubleshooting

**Owner:** Development/DevOps | **Frequency:** Daily (before market hours)
**Last Updated:** 2026-03-25 | **Next Review:** 2026-04-01

---

## 📋 Purpose

Start and verify the StockGuru Flask API server on port 5050. This runbook is used:
- Daily before market open (9:00 AM IST)
- When API endpoints are unresponsive
- After system restart
- When deploying new agent modules

---

## ✅ Prerequisites

Before starting Flask, verify you have:
- [ ] Python 3.8+ installed
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Port 5050 available (not blocked by firewall)
- [ ] Data directory exists: `./data/`
- [ ] Agent modules present: `./stockguru_agents/`
- [ ] n8n running (optional but recommended)

**Check Python version:**
```bash
python --version
# Expected: Python 3.8 or higher
```

**Check port availability:**
```bash
# On Windows:
netstat -ano | find "5050"

# On Linux/Mac:
lsof -i :5050
```

If port 5050 is in use: Kill process or use different port

---

## 🚀 Procedure

### Step 1: Navigate to Project Directory
```bash
cd C:\Users\Hp\projects\stockguru
# Or your actual project path
```
**Expected result**: Command prompt shows `stockguru` directory
**If it fails**: Check path is correct, adjust as needed

---

### Step 2: Verify Requirements Installed
```bash
pip list | grep -i flask
```
**Expected output**:
```
Flask
Flask-CORS
Flask-SocketIO
gunicorn
```

**If missing**, install:
```bash
pip install -r requirements.txt
```

---

### Step 3: Start Flask Server
```bash
python app.py
```

**Expected output** (in console):
```
 * Running on http://127.0.0.1:5050
 * Press CTRL+C to quit
 * Debugger is active!
 * Debugger PIN: 123-456-789
```

⚠️ **Important**: Keep terminal open while Flask is running

**If it fails**: See **Troubleshooting** section below

---

### Step 4: Verify Server is Running (New Terminal)

Open **new command prompt** (don't close the one running Flask):

```bash
# Test basic health check
curl http://localhost:5050/api/health

# Or on Windows without curl:
powershell -Command "(New-Object System.Net.WebClient).DownloadString('http://localhost:5050/api/health')"
```

**Expected response**:
```json
{"status": "ok", "timestamp": "2026-03-25T..."}
```

**If it fails**: Flask not responding (see Troubleshooting)

---

### Step 5: Run System Diagnostics
```bash
python DIAGNOSIS_TOOLKIT.py
```

**Expected output**:
```
✅ Flask server is running
✅ Agent endpoints responding
✅ WebSocket available
```

**If Flask shows as offline**: Check terminal running Flask, check port 5050

---

## ✔️ Verification Checklist

After starting Flask, verify:

- [ ] Console shows "Running on http://127.0.0.1:5050"
- [ ] No error messages in console
- [ ] Health check endpoint responds (Step 4)
- [ ] DIAGNOSIS_TOOLKIT.py shows Flask: running
- [ ] No "Port already in use" error
- [ ] All required data files exist (./data/)

---

## 🔧 Troubleshooting

### Symptom 1: Port 5050 Already in Use
**Error**:
```
Address already in use
OSError: [Errno 48] Address already in use
```

**Likely Cause**: Another process using port 5050, or Flask already running

**Fix**:
```bash
# Find process using port 5050
netstat -ano | find "5050"

# Kill process by PID (replace 12345 with actual PID)
taskkill /PID 12345 /F

# Then try starting Flask again
python app.py
```

**Alternative**: Use different port:
```bash
# Edit app.py, change:
# app.run(host='127.0.0.1', port=5050)
# to:
# app.run(host='127.0.0.1', port=5051)
```

---

### Symptom 2: ModuleNotFoundError (Import Error)
**Error**:
```
ModuleNotFoundError: No module named 'flask'
ModuleNotFoundError: No module named 'flask_socketio'
```

**Likely Cause**: Dependencies not installed

**Fix**:
```bash
# Install all requirements
pip install -r requirements.txt

# Or install specific module
pip install flask flask-cors flask-socketio

# Then try again
python app.py
```

---

### Symptom 3: Agent Modules Missing
**Error** (in diagnostics):
```
❌ market_scanner.py missing
❌ news_sentiment.py missing
...
```

**Likely Cause**: Agent files not in ./stockguru_agents/ directory

**Fix**:
```bash
# Check if directory exists
ls stockguru_agents/

# If missing agents:
# Option 1: Create directory if missing
mkdir stockguru_agents

# Option 2: Check if agents are defined in app.py instead
# Look in app.py for agent function definitions

# Option 3: Copy agents from backup
# (Get from version control or backup)
```

---

### Symptom 4: No Response on Health Check
**Error**:
```
curl: (7) Failed to connect to localhost port 5050: Connection refused
```

**Likely Cause**: Flask running but not responding, port not bound correctly

**Fix**:
```bash
# Check if Flask console shows errors
# Look for red error messages

# Verify Flask is listening on correct address
# In app.py, ensure:
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5050, debug=True)

# Restart Flask:
# 1. Press Ctrl+C in Flask terminal
# 2. Run: python app.py
```

---

### Symptom 5: WebSocket Not Working
**Warning** (in diagnostics):
```
⚠️ WebSocket endpoint not accessible
```

**Likely Cause**: Flask-SocketIO not initialized in app.py

**Fix**:
```bash
# Verify flask_socketio is installed
pip install flask-socketio gevent gevent-websocket

# Check app.py has:
from flask_socketio import SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# If missing, add those lines to app.py
```

---

### Symptom 6: Agent Endpoints Return 404
**Error**:
```
❌ /api/scanner (status: 404)
❌ /api/signals (status: 404)
```

**Likely Cause**: Routes not defined in app.py, or agents not loaded

**Fix**:
```bash
# In app.py, verify routes exist:
@app.route('/api/scanner', methods=['GET'])
def api_scanner():
    # Should return agent output

# If routes missing, check:
# 1. Are agents defined in app.py?
# 2. Are routes using correct paths?
# 3. Did diagnostics run BEFORE Flask was started?

# Re-run diagnostics AFTER Flask is running
python DIAGNOSIS_TOOLKIT.py
```

---

## 🔙 Rollback

If Flask server is causing issues:

```bash
# Stop Flask (in Flask terminal)
Ctrl+C

# Verify it stopped
curl http://localhost:5050/api/health
# Should fail with "connection refused"

# Revert to previous version (if in git)
git checkout app.py
git pull

# Start Flask again
python app.py
```

---

## 🚨 Escalation

| Situation | Contact | Method |
|-----------|---------|--------|
| Port 5050 blocked by firewall | IT/DevOps | Email or ticket |
| Persistent ModuleNotFoundError | Tech Lead | Slack - request help with requirements.txt |
| Agent modules corrupted | Development Team | Ask for fresh copy from repo |
| Database locked/corrupted | DBA | Database reset needed |
| Performance degradation (> 5s per request) | Performance Engineer | Profile app.py for bottlenecks |

---

## 📊 Health Check Quick Reference

```bash
# Quick health checks (all in one command on Windows):
echo Testing Flask... && ^
curl http://localhost:5050/api/health && ^
echo.&echo Testing agents... && ^
python DIAGNOSIS_TOOLKIT.py
```

---

## 📝 Execution Log

| Date | Time | Started By | Status | Notes |
|------|------|-----------|--------|-------|
| 2026-03-25 | 10:15 | Bharathi | ✅ Success | First startup, all tests passed |
| | | | | |
| | | | | |

*Update this table after each run*

---

## 📚 Related Documentation

- **AGENTIC_ECOSYSTEM_MASTER_PLAN.md** - Full architecture overview
- **IMPLEMENTATION_QUICKSTART.md** - Implementation phases
- **DIAGNOSIS_TOOLKIT.py** - Automated health checker
- **app.py** - Main Flask application

---

## 💡 Pro Tips

1. **Always keep Flask terminal open** while working
2. **Run diagnostics regularly** to catch issues early
3. **Check logs daily** for errors before they accumulate
4. **Restart Flask daily** (not just running continuously)
5. **Use Debug mode** during development (already enabled in app.py)

---

## ✅ Verification After Startup

After successfully starting Flask, verify:

```bash
# 1. Flask is running
curl http://localhost:5050/api/health
# Should return: {"status": "ok", ...}

# 2. Agents are loading (check console for no errors)
# Look for: "✅ Agent: market_scanner registered"

# 3. Run full diagnostics
python DIAGNOSIS_TOOLKIT.py
# Should show: ✅ Flask server is running

# 4. Check data persistence
ls -la ./data/
# Should show: paper_trades.json, portfolio.json, etc.
```

---

**Status**: Ready to Use | **Last Tested**: 2026-03-25 | **Valid Until**: 2026-04-25
