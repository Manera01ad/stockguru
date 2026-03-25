# src/ - Source Code Directory

**Purpose**: All active production and development code lives here.

## Structure

```
src/
├── core/                 # Main orchestration & validation engines
├── agents/              # 14-agent coordination modules
├── api/                 # Flask API routes & MCP server
├── models/              # Data models & ORM definitions
└── utils/               # Helper utilities & diagnostics
```

## Key Files

### core/
- **app.py** - Flask application entry point, route handlers
- **agent_orchestrator.py** - Coordinates 14 agents, fallback chains
- **conviction_filter.py** - 8-gate trade validation filter
- **agentic_report_generator.py** - Generates decision reports

### agents/
- **models.py** - SQLAlchemy ORM (Trade, Signal, ConvictionAudit tables)
- Agent modules imported from stockguru_agents/ package

### api/
- **app_routes.py** - RESTful endpoints for web UI
- **mcp_server.py** - Claude MCP integration
- **api_check.py** - Endpoint validation & health checks

### utils/
- **diagnostics/** - Debugging tools (check_*, fix_* scripts)
- **restart_server.py** - Deployment helper
- **merge_tabs.py** - Data processing utility

## Import Convention

All imports use absolute paths from src/:

```python
# ✅ Correct
from src.core.conviction_filter import ConvictionFilter
from src.agents.models import Trade
from src.utils.diagnostics.check_ids import verify_ids

# ❌ Avoid (relative imports)
from ..core.conviction_filter import ConvictionFilter
```

## Adding New Code

1. **New module?** Create in appropriate subdirectory (core, agents, api, utils)
2. **New agent?** Add to agents/ directory
3. **New API endpoint?** Add to api/ with route handler
4. **New helper?** Add to utils/ with clear naming

**Never add Python files to src/ root level.**

---

*DSA Principle: Keep src/ as pure source code, no configuration or tests.*
