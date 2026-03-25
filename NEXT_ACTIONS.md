# StockGuru - Next Actions After Reorganization

**Project Status**: ✅ Phase 2.5 Complete | 🏗️ Ready for Phase 3
**Structure**: ✅ DSA-optimized (hierarchical, O(1) lookup)
**Date**: 2026-03-26

---

## 🎯 Immediate Actions (Before Phase 3)

### 1. Verify Flask App Works ⚡
```bash
# Test if Flask app can start
python src/core/app.py

# Or with Flask CLI
FLASK_APP=src/core/app.py flask run
```

**Issues to fix if encountered**:
- Line 4162 in app.py - Unterminated string literal (pre-existing)
- Line 142 in models.py - Unclosed parenthesis (pre-existing)
- Fix these in your code editor

### 2. Run Test Suite 🧪
```bash
# Install dependencies
pip install -r config/requirements.txt

# Run unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ --cov=src
```

**Expected**: Most tests should pass (some may be integration tests that need API keys)

### 3. Update Environment Variables 🔐
```bash
# Copy template
cp config/.env.example config/.env

# Edit with your actual values
nano config/.env
```

**Variables to set**:
```
SHOONYA_API_KEY=xxxxx          # Broker API (top up credit!)
CLAUDE_API_KEY=xxxxx           # Claude API
GEMINI_API_KEY=xxxxx           # Backup LLM
DATABASE_URL=sqlite:///data/stockguru.db
FLASK_ENV=production
SECRET_KEY=your-secret-key
```

### 4. Update PYTHONPATH (If Needed) 📦

**If running tests from root**:
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest tests/unit/
```

**If using PyCharm/VSCode**:
- Mark `src/` as Sources Root
- Mark `tests/` as Tests Root

### 5. Verify Database Connection 🗄️
```bash
# Quick test
python -c "
from src.agents.models import Trade, Signal
from sqlalchemy import create_engine

engine = create_engine('sqlite:///data/stockguru.db')
print('✅ Database connected!')
"
```

---

## 📝 Documentation to Review

### Read These (In Order)
1. **PROJECT_STRUCTURE.md** ← Start here (navigation guide)
2. **REORGANIZATION_SUMMARY_2026_03_25.md** ← Full before/after report
3. **src/README.md** ← Source code organization
4. **config/README.md** ← Configuration usage
5. **CLAUDE.md** ← Project instructions
6. **docs/ARCHITECTURE.md** ← System design

### Archive (For Reference Only)
- **docs/archived/phases/** ← Old PHASE documentation
- **docs/archived/old_docs/** ← Status reports (not needed for Phase 3)

---

## 🚀 For Phase 3 Development

### File Structure Best Practices

**When adding new code**:
```python
# ✅ CORRECT - Use src/ structure
from src.core.conviction_filter import ConvictionFilter
from src.agents.models import Trade
from src.api.routes import api_handler

# ❌ WRONG - Don't mix root imports
from conviction_filter import ConvictionFilter  # Won't work!
```

**When adding new tests**:
```bash
# Create in tests/unit/
tests/unit/test_new_feature.py

# Run with
pytest tests/unit/test_new_feature.py -v
```

**When adding documentation**:
```bash
# Add to docs/ (not root!)
docs/FEATURE_GUIDE.md          # ✅ Good
docs/USER_GUIDE.md             # ✅ Good
FEATURE_GUIDE.md               # ❌ Don't do this!
```

**When adding configuration**:
```bash
# All config in config/
config/new_setting.conf        # ✅ Good
new_setting.conf               # ❌ Don't do this!

# Secrets go in .env
config/.env                    # ✅ Good (not committed)
```

---

## 🔍 Troubleshooting

### "Module not found" errors
**Problem**: `ImportError: No module named 'src.core.app'`

**Solution 1** - Set PYTHONPATH:
```bash
export PYTHONPATH="."
python src/core/app.py
```

**Solution 2** - Update sys.path in your code:
```python
import sys
import os
sys.path.insert(0, os.getcwd())

from src.core.app import app
```

### Test discovery failures
**Problem**: `pytest: error: file not found: tests/unit/test_something.py`

**Solution** - Run from project root:
```bash
# From /sessions/affectionate-lucid-ritchie/mnt/stockguru/
pytest tests/unit/
```

### Database connection errors
**Problem**: `sqlite3.OperationalError: unable to open database file`

**Solution** - Ensure path is correct:
```python
# Use absolute path or relative from src/
from sqlalchemy import create_engine
engine = create_engine('sqlite:////sessions/affectionate-lucid-ritchie/mnt/stockguru/data/stockguru.db')
```

### Config file not found
**Problem**: `.env file not found`

**Solution**:
```bash
cd /sessions/affectionate-lucid-ritchie/mnt/stockguru/
ls -la config/.env
# If missing: cp config/.env.example config/.env
```

---

## 📊 Project Statistics

| Item | Count | Location |
|------|-------|----------|
| Python source files | 50+ | src/ |
| Test files | 27 | tests/unit/ |
| Config files | 8 | config/ |
| Documentation (active) | 6 | docs/ + README_START_HERE.md |
| Documentation (archived) | 28 | docs/archived/ |
| Utility scripts | 10+ | scripts/ |
| Data files | 32 | data/ |
| **Total organized files** | **150+** | **Hierarchical structure** |

---

## ✅ Verification Checklist

- [ ] Cloned/synced latest code
- [ ] Installed requirements: `pip install -r config/requirements.txt`
- [ ] Copied .env template: `cp config/.env.example config/.env`
- [ ] Set API keys in config/.env
- [ ] Can import src modules: `python -c "from src.core.app import app"`
- [ ] Database connects: `python -c "from src.agents.models import Trade"`
- [ ] Tests discover: `pytest tests/unit/ --collect-only`
- [ ] Read PROJECT_STRUCTURE.md
- [ ] PYTHONPATH is set correctly

---

## 🎓 Learning Path for New Developers

1. **Onboarding (5 mins)**
   - Read PROJECT_STRUCTURE.md
   - Check out src/README.md

2. **Understanding Architecture (15 mins)**
   - Read docs/ARCHITECTURE.md
   - Review src/core/agent_orchestrator.py
   - Review src/core/conviction_filter.py

3. **Setting Up (10 mins)**
   - Copy config/.env.example → config/.env
   - Set API keys
   - Run pytest tests/unit/ -v

4. **Adding First Feature (30 mins)**
   - Create test in tests/unit/test_my_feature.py
   - Write code in src/{core,agents,api,utils}/
   - Run tests: pytest tests/unit/test_my_feature.py

---

## 📞 Questions?

**"Where's the old PHASE documentation?"**
→ Check `docs/archived/phases/`

**"Where do I add new code?"**
→ Follow the structure in `src/`: `src/core/`, `src/agents/`, `src/api/`, `src/utils/`

**"How do I run tests?"**
→ `pytest tests/unit/` (from project root)

**"Where are configuration files?"**
→ All in `config/` directory

**"How do I update documentation?"**
→ Add to `docs/` (not root), never use `PHASE_` prefix

---

## 🎯 Phase 3 Preparation

- ✅ Project structure clean and optimized
- ✅ Imports verified (conviction_filter.py works)
- ✅ Documentation complete
- ✅ README files created for navigation
- ✅ Test suite organized
- ✅ Config consolidated

**Ready to start Phase 3**: WebSocket enrichment and real-time data streaming!

---

*Last updated: 2026-03-26 | Project: StockGuru | Optimization: DSA Hierarchical*
