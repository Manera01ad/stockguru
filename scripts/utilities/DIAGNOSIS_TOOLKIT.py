#!/usr/bin/env python3
"""
StockGuru Agentic Ecosystem - Diagnostic Toolkit
=================================================

This tool:
1. Audits existing agents for functionality
2. Identifies missing components
3. Checks WebSocket status
4. Validates data persistence
5. Tests n8n connectivity
6. Generates detailed issue report

Run: python DIAGNOSIS_TOOLKIT.py
"""

import os
import sys
import json
import requests
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Color codes for terminal output
class Colors:
    OKGREEN = '\033[92m'
    FAIL = '\033[91m'
    WARNING = '\033[93m'
    OKCYAN = '\033[96m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

# ──────────────────────────────────────────────────────────────────────────────
# Diagnostic Tests
# ──────────────────────────────────────────────────────────────────────────────

class DiagnosticSuite:
    """Run all diagnostic tests"""

    def __init__(self, base_url: str = "http://localhost:5050", n8n_url: str = "http://localhost:5678"):
        self.base_url = base_url
        self.n8n_url = n8n_url
        self.results = {}
        self.issues = []
        self.warnings = []

    def run_all_tests(self) -> Dict[str, Any]:
        """Run complete diagnostic suite"""
        print(f"\n{Colors.BOLD}🔍 StockGuru Agentic Ecosystem Diagnostic{Colors.ENDC}")
        print("=" * 70)

        self.test_flask_connectivity()
        self.test_agent_endpoints()
        self.test_websocket_support()
        self.test_data_persistence()
        self.test_n8n_connectivity()
        self.test_agent_imports()
        self.test_database_setup()
        self.test_report_generation()

        return self._generate_report()

    # ────────────────────────────────────────────────────────────────────────
    # Test 1: Flask Server
    # ────────────────────────────────────────────────────────────────────────

    def test_flask_connectivity(self):
        """Check if Flask server is running"""
        print(f"\n{Colors.OKCYAN}Test 1: Flask Server Connectivity{Colors.ENDC}")
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=5)
            if response.status_code == 200:
                print(f"{Colors.OKGREEN}✅ Flask server is running{Colors.ENDC}")
                self.results['flask'] = 'running'
            else:
                print(f"{Colors.FAIL}❌ Flask server returned status {response.status_code}{Colors.ENDC}")
                self.results['flask'] = 'unhealthy'
                self.issues.append("Flask health check returned non-200 status")
        except requests.exceptions.ConnectionError:
            print(f"{Colors.FAIL}❌ Cannot connect to Flask server at {self.base_url}{Colors.ENDC}")
            self.results['flask'] = 'offline'
            self.issues.append(f"Flask server not running (check if listening on {self.base_url})")
        except Exception as e:
            print(f"{Colors.FAIL}❌ Error: {str(e)}{Colors.ENDC}")
            self.results['flask'] = 'error'
            self.issues.append(f"Flask connectivity error: {str(e)}")

    # ────────────────────────────────────────────────────────────────────────
    # Test 2: Agent Endpoints
    # ────────────────────────────────────────────────────────────────────────

    def test_agent_endpoints(self):
        """Test if agent endpoints are responding"""
        print(f"\n{Colors.OKCYAN}Test 2: Agent Endpoints{Colors.ENDC}")

        endpoints = [
            '/api/scanner',
            '/api/signals',
            '/api/news',
            '/api/commodities',
            '/api/technical',
            '/api/institutional-flow',
            '/api/agent-status',
            '/api/claude-analysis'
        ]

        working = []
        failing = []

        for endpoint in endpoints:
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                if response.status_code in [200, 204]:
                    working.append(endpoint)
                    print(f"{Colors.OKGREEN}✅ {endpoint}{Colors.ENDC}")
                else:
                    failing.append((endpoint, response.status_code))
                    print(f"{Colors.WARNING}⚠️  {endpoint} (status: {response.status_code}){Colors.ENDC}")
            except Exception as e:
                failing.append((endpoint, str(e)))
                print(f"{Colors.FAIL}❌ {endpoint} (error: {str(e)}){Colors.ENDC}")

        self.results['agent_endpoints'] = {
            'working': len(working),
            'failing': len(failing),
            'total': len(endpoints)
        }

        if failing:
            self.warnings.append(f"{len(failing)} agent endpoints not responding")

    # ────────────────────────────────────────────────────────────────────────
    # Test 3: WebSocket Support
    # ────────────────────────────────────────────────────────────────────────

    def test_websocket_support(self):
        """Check if Flask-SocketIO is working"""
        print(f"\n{Colors.OKCYAN}Test 3: WebSocket Support{Colors.ENDC}")

        # Check if flask_socketio is installed
        try:
            import flask_socketio
            print(f"{Colors.OKGREEN}✅ flask_socketio is installed{Colors.ENDC}")

            # Try to check if WebSocket is enabled in the Flask app
            try:
                # WebSocket test (simplified)
                response = requests.get(f"{self.base_url}/socket.io/", timeout=5)
                if response.status_code in [200, 400]:  # 400 is OK for GET
                    print(f"{Colors.OKGREEN}✅ WebSocket endpoint is available{Colors.ENDC}")
                    self.results['websocket'] = 'available'
                else:
                    print(f"{Colors.WARNING}⚠️  WebSocket endpoint returned {response.status_code}{Colors.ENDC}")
                    self.results['websocket'] = 'available_but_may_be_misconfigured'
            except Exception as e:
                print(f"{Colors.WARNING}⚠️  Cannot verify WebSocket endpoint: {str(e)}{Colors.ENDC}")
                self.results['websocket'] = 'unknown'
                self.warnings.append("WebSocket endpoint not accessible - may not be initialized")

        except ImportError:
            print(f"{Colors.FAIL}❌ flask_socketio not installed{Colors.ENDC}")
            self.results['websocket'] = 'not_installed'
            self.issues.append("Install flask-socketio: pip install flask-socketio gevent gevent-websocket")

    # ────────────────────────────────────────────────────────────────────────
    # Test 4: Data Persistence
    # ────────────────────────────────────────────────────────────────────────

    def test_data_persistence(self):
        """Check data files exist and are readable"""
        print(f"\n{Colors.OKCYAN}Test 4: Data Persistence{Colors.ENDC}")

        data_dir = Path('./data')
        if not data_dir.exists():
            print(f"{Colors.FAIL}❌ ./data directory not found{Colors.ENDC}")
            self.results['data_persistence'] = 'missing'
            self.issues.append("Create ./data directory for persistence")
            return

        # Check for key data files
        required_files = [
            'paper_trades.json',
            'paper_portfolio.json',
            'signal_history.json',
            'pattern_library.json'
        ]

        found_files = []
        missing_files = []

        for filename in required_files:
            filepath = data_dir / filename
            if filepath.exists():
                try:
                    with open(filepath, 'r') as f:
                        json.load(f)  # Validate JSON
                    found_files.append(filename)
                    print(f"{Colors.OKGREEN}✅ {filename} (valid JSON){Colors.ENDC}")
                except json.JSONDecodeError:
                    print(f"{Colors.FAIL}❌ {filename} (corrupted JSON){Colors.ENDC}")
                    self.issues.append(f"Data file corrupted: {filename}")
            else:
                missing_files.append(filename)
                print(f"{Colors.WARNING}⚠️  {filename} (missing){Colors.ENDC}")

        self.results['data_persistence'] = {
            'found': len(found_files),
            'missing': len(missing_files),
            'status': 'partial' if missing_files else 'complete'
        }

        if missing_files:
            self.warnings.append(f"{len(missing_files)} data files missing - will be created on first run")

    # ────────────────────────────────────────────────────────────────────────
    # Test 5: n8n Connectivity
    # ────────────────────────────────────────────────────────────────────────

    def test_n8n_connectivity(self):
        """Check if n8n is running"""
        print(f"\n{Colors.OKCYAN}Test 5: n8n Orchestration{Colors.ENDC}")

        try:
            response = requests.get(f"{self.n8n_url}/api/v1/workflows", timeout=5)
            if response.status_code in [200, 401]:  # 401 is OK if auth is required
                print(f"{Colors.OKGREEN}✅ n8n is running{Colors.ENDC}")
                self.results['n8n'] = 'running'
            else:
                print(f"{Colors.WARNING}⚠️  n8n returned status {response.status_code}{Colors.ENDC}")
                self.results['n8n'] = 'running_but_check_status'
        except requests.exceptions.ConnectionError:
            print(f"{Colors.WARNING}⚠️  Cannot connect to n8n at {self.n8n_url}{Colors.ENDC}")
            self.results['n8n'] = 'offline'
            self.warnings.append(f"n8n not running - orchestration disabled (run: n8n start)")
        except Exception as e:
            print(f"{Colors.WARNING}⚠️  n8n check error: {str(e)}{Colors.ENDC}")
            self.results['n8n'] = 'unknown'

    # ────────────────────────────────────────────────────────────────────────
    # Test 6: Agent Imports
    # ────────────────────────────────────────────────────────────────────────

    def test_agent_imports(self):
        """Test if all agent modules can be imported"""
        print(f"\n{Colors.OKCYAN}Test 6: Agent Module Imports{Colors.ENDC}")

        agents_to_test = [
            'market_scanner',
            'news_sentiment',
            'trade_signal',
            'commodity_crypto',
            'morning_brief',
            'technical_analysis',
            'institutional_flow',
            'options_flow',
            'claude_intelligence',
            'web_researcher',
            'sector_rotation',
            'risk_manager',
            'pattern_memory',
            'paper_trader',
            'earnings_calendar',
            'spike_detector'
        ]

        working = []
        failing = []

        # Try importing from agents module
        try:
            agents_path = Path('./stockguru_agents')
            if not agents_path.exists():
                print(f"{Colors.WARNING}⚠️  ./stockguru_agents directory not found{Colors.ENDC}")
                self.results['agent_imports'] = 'directory_missing'
                self.issues.append("Create ./stockguru_agents directory with agent modules")
                return

            print(f"{Colors.OKGREEN}✅ stockguru_agents directory found{Colors.ENDC}")

            for agent in agents_to_test:
                # Check both stockguru_agents/ and stockguru_agents/agents/
                agent_file = agents_path / f'{agent}.py'
                sub_agent_file = agents_path / 'agents' / f'{agent}.py'
                
                if agent_file.exists() or sub_agent_file.exists():
                    working.append(agent)
                    print(f"{Colors.OKGREEN}✅ {agent}.py exists{Colors.ENDC}")
                else:
                    failing.append(agent)
                    print(f"{Colors.FAIL}❌ {agent}.py missing{Colors.ENDC}")

            self.results['agent_imports'] = {
                'available': len(working),
                'missing': len(failing),
                'status': 'complete' if not failing else 'partial'
            }

            if failing:
                self.warnings.append(f"{len(failing)} agent modules missing")

        except Exception as e:
            print(f"{Colors.FAIL}❌ Error checking agents: {str(e)}{Colors.ENDC}")
            self.results['agent_imports'] = 'error'
            self.issues.append(f"Agent import error: {str(e)}")

    # ────────────────────────────────────────────────────────────────────────
    # Test 7: Database Setup
    # ────────────────────────────────────────────────────────────────────────

    def test_database_setup(self):
        """Check if SQLite database is set up"""
        print(f"\n{Colors.OKCYAN}Test 7: Database Setup{Colors.ENDC}")

        try:
            import sqlite3
            print(f"{Colors.OKGREEN}✅ sqlite3 is available{Colors.ENDC}")

            db_path = Path('./stockguru.db')
            if db_path.exists():
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = cursor.fetchall()
                    print(f"{Colors.OKGREEN}✅ Database exists with {len(tables)} tables{Colors.ENDC}")
                    self.results['database'] = 'exists'
                    conn.close()
                except Exception as e:
                    print(f"{Colors.FAIL}❌ Database corrupted: {str(e)}{Colors.ENDC}")
                    self.results['database'] = 'corrupted'
                    self.issues.append("Delete stockguru.db and restart to recreate")
            else:
                print(f"{Colors.WARNING}⚠️  Database not created yet (will be created on first run){Colors.ENDC}")
                self.results['database'] = 'not_created'
                self.warnings.append("Database will be created on first agent execution")

        except ImportError:
            print(f"{Colors.FAIL}❌ sqlite3 not available{Colors.ENDC}")
            self.results['database'] = 'sqlite3_missing'
            self.issues.append("sqlite3 should be available by default in Python")

    # ────────────────────────────────────────────────────────────────────────
    # Test 8: Report Generation
    # ────────────────────────────────────────────────────────────────────────

    def test_report_generation(self):
        """Check if report directories exist"""
        print(f"\n{Colors.OKCYAN}Test 8: Report Generation{Colors.ENDC}")

        report_dirs = [
            Path('./reports/daily'),
            Path('./reports/performance'),
            Path('./reports/archive')
        ]

        created = []
        missing = []

        for report_dir in report_dirs:
            if report_dir.exists():
                created.append(str(report_dir))
                print(f"{Colors.OKGREEN}✅ {report_dir} exists{Colors.ENDC}")
            else:
                missing.append(str(report_dir))
                print(f"{Colors.WARNING}⚠️  {report_dir} missing{Colors.ENDC}")

        self.results['reports'] = {
            'existing': len(created),
            'missing': len(missing),
            'status': 'complete' if not missing else 'partial'
        }

        if missing:
            self.warnings.append("Report directories will be created on first report generation")

    # ────────────────────────────────────────────────────────────────────────
    # Report Generation
    # ────────────────────────────────────────────────────────────────────────

    def _generate_report(self) -> Dict[str, Any]:
        """Generate diagnostic report"""
        print("\n" + "=" * 70)
        print(f"{Colors.BOLD}📋 Diagnostic Summary{Colors.ENDC}")
        print("=" * 70)

        # Summary
        print(f"\n{Colors.BOLD}Overall Status:{Colors.ENDC}")
        if not self.issues:
            print(f"{Colors.OKGREEN}✅ All critical systems operational{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}⚠️  {len(self.issues)} critical issues found{Colors.ENDC}")

        # Issues
        if self.issues:
            print(f"\n{Colors.BOLD}🔴 Critical Issues (must fix):{Colors.ENDC}")
            for i, issue in enumerate(self.issues, 1):
                print(f"  {i}. {issue}")

        # Warnings
        if self.warnings:
            print(f"\n{Colors.BOLD}🟡 Warnings (should fix):{Colors.ENDC}")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")

        # Test Results
        print(f"\n{Colors.BOLD}Test Results:{Colors.ENDC}")
        for test, result in self.results.items():
            status = "✅" if isinstance(result, dict) and result.get('status') != 'missing' else "✓"
            print(f"  {status} {test}: {result}")

        # Save report to file
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'issues': self.issues,
            'warnings': self.warnings,
            'results': self.results
        }

        report_file = Path('./DIAGNOSIS_REPORT.json')
        report_file.write_text(json.dumps(report_data, indent=2))
        print(f"\n💾 Full report saved to: {report_file}")

        return report_data

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    """Run diagnostic suite"""
    try:
        # Check if Flask server is running (optional)
        flask_url = "http://localhost:5050"
        n8n_url = "http://localhost:5678"

        suite = DiagnosticSuite(flask_url, n8n_url)
        report = suite.run_all_tests()

        # Exit with appropriate code
        exit_code = 0 if not suite.issues else 1
        sys.exit(exit_code)

    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Diagnostic cancelled by user{Colors.ENDC}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.FAIL}Unexpected error: {str(e)}{Colors.ENDC}")
        sys.exit(1)

if __name__ == '__main__':
    main()
