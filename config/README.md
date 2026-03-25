# config/ - Configuration Directory

**Purpose**: Consolidated configuration files for the entire project.

## Files

| File | Purpose | Committed? |
|------|---------|-----------|
| .env | Runtime environment variables (secrets) | ❌ NO - in .gitignore |
| .env.example | Template for .env (no real values) | ✅ YES |
| gunicorn.conf.py | WSGI web server settings | ✅ YES |
| mcp_config.json | Claude MCP server configuration | ✅ YES |
| requirements.txt | Python package dependencies | ✅ YES |
| pytest.ini | Test runner configuration | ✅ YES |
| railway.json | Railway.app deployment config | ✅ YES |
| runtime.txt | Python version specification | ✅ YES |
| nixpacks.toml | Nix package configuration | ✅ YES |

## Usage

### Loading Configuration
```python
# In app.py or main entry point
from dotenv import load_dotenv
load_dotenv('config/.env')

import os
API_KEY = os.getenv('SHOONYA_API_KEY')
```

### Adding New Config
1. Add variable to config/.env.example
2. Add actual value to config/.env
3. Load in Python code: `os.getenv('VAR_NAME')`

### Common Variables
```
SHOONYA_API_KEY=xxxxx        # Broker API
GEMINI_API_KEY=xxxxx         # Secondary LLM
CLAUDE_API_KEY=xxxxx         # Primary LLM
DATABASE_URL=sqlite:///stockguru.db
FLASK_ENV=development
```

## Security

⚠️ **CRITICAL**:
- ❌ NEVER commit .env (has real secrets)
- ✅ Commit .env.example (as template only)
- ✅ Add .env to .gitignore
- ✅ Use environment variables for secrets

---

*DSA Principle: Single source of truth for configuration - all config in one place.*
