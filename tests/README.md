# tests/ - Test Suite Directory

**Purpose**: All test code organized by testing category (unit, integration, etc.)

## Structure

```
tests/
├── unit/                # Unit tests (15+ files)
│   ├── test_nse.py
│   ├── test_shoonya*.py
│   ├── test_sovereign*.py
│   ├── test_gemini.py
│   ├── test_login.py
│   ├── test_oc.py
│   ├── test_ia.py
│   └── ... other unit tests
│
└── integration/         # Integration tests (Phase 3+)
    └── (empty - to be populated)
```

## Running Tests

```bash
# Run all tests
pytest tests/

# Run only unit tests
pytest tests/unit/

# Run specific test file
pytest tests/unit/test_nse.py

# Run with verbose output
pytest tests/unit/ -v

# Run and show print statements
pytest tests/unit/ -s
```

## Adding New Tests

1. Create file: tests/unit/test_<feature>.py
2. Follow naming: test_*.py pattern
3. Use pytest conventions:
   ```python
   def test_something_works():
       result = some_function()
       assert result == expected
   ```

4. Run: `pytest tests/unit/test_<feature>.py`

## Test Categories

### Unit Tests (tests/unit/)
- **test_nse.py** - NSE broker connection
- **test_shoonya*.py** - Shoonya broker tests
- **test_sovereign*.py** - Sovereign broker logic
- **test_gemini.py** - Gemini LLM integration
- **test_login.py** - Authentication tests
- **test_oc.py**, **test_ia.py** - Option chain, implied vol tests
- **test_yf_opts.py** - Yahoo Finance options parsing

### Integration Tests (tests/integration/) - *Phase 3*
- Full workflow testing (agent → broker → database)
- Multi-agent coordination tests
- End-to-end trade execution tests

## Configuration

**pytest.ini** (in config/ directory):
```ini
[pytest]
python_files = test_*.py
testpaths = tests
addopts = -v
```

## Coverage

To measure test coverage:
```bash
pip install pytest-cov
pytest tests/ --cov=src
```

---

*DSA Principle: Organize tests by type (unit, integration), not by location.*
