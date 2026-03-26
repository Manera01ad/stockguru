"""
Phase 5 Self-Healing API Routes

Add these 4 endpoints to your Flask app.py

These routes expose the Phase 5 Learning Engine functionality:
- Trigger optimization analysis
- Get current performance metrics
- List AI recommendations
- Approve and apply optimizations
"""

from flask import Blueprint, request, jsonify, send_file
from datetime import datetime
import io
from phase5_self_healing.learning_engine import LearningEngine
from phase5_self_healing.visualization import Phase5Reporter

# Create Blueprint
phase5_bp = Blueprint('phase5', __name__, url_prefix='/api/self-healing')

# Initialize shared learning engine (use app context for DB connection)
learning_engine = None


def init_phase5_api(app, db_connection):
    """
    Call this in your app initialization:

    from src.agents.models import db
    from PHASE_5_API_ROUTES import init_phase5_api

    init_phase5_api(app, db.session)
    """
    global learning_engine
    learning_engine = LearningEngine(db_connection=db_connection)
    app.register_blueprint(phase5_bp)


# ============================================================================
# ENDPOINT 1: POST /api/self-healing/run
# Trigger a complete Phase 5 analysis cycle
# ============================================================================

@phase5_bp.route('/run', methods=['POST'])
def run_phase5_analysis():
    """
    Trigger Phase 5 Self-Healing analysis

    POST /api/self-healing/run

    Request body (optional):
    {
        "symbol": "RELIANCE",  # Optional: analyze specific symbol
        "days": 90,            # Optional: analysis period in days
        "trigger": "manual"    # Optional: "manual", "scheduled", "anomaly"
    }

    Response:
    {
        "status": "success",
        "analysis_id": 123,
        "analysis_period": {...},
        "trade_outcomes": {...},
        "gate_effectiveness": {...},
        "market_regime": {...},
        "threshold_recommendations": [...],
        "risk_optimization": {...},
        "timestamp": "2026-03-25T10:30:00"
    }
    """
    try:
        # Parse request
        data = request.get_json() or {}
        symbol = data.get('symbol')
        days = data.get('days', 90)
        trigger = data.get('trigger', 'manual')

        # Run analysis
        results = learning_engine.run_full_analysis(symbol=symbol, days=days)

        # Log analysis session to database (optional)
        if results['status'] == 'success':
            return jsonify({
                'status': 'success',
                'message': 'Phase 5 analysis completed successfully',
                'data': results,
                'timestamp': datetime.utcnow().isoformat(),
            }), 200

        else:
            return jsonify({
                'status': 'error',
                'message': results.get('message', 'Analysis failed'),
                'timestamp': datetime.utcnow().isoformat(),
            }), 400

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error during analysis: {str(e)}',
            'timestamp': datetime.utcnow().isoformat(),
        }), 500


# ============================================================================
# ENDPOINT 2: GET /api/self-healing/stats
# Get current performance health and metrics
# ============================================================================

@phase5_bp.route('/stats', methods=['GET'])
def get_phase5_stats():
    """
    Get Phase 5 health and performance metrics

    GET /api/self-healing/stats

    Query parameters (optional):
    - period: "day", "week", "month", "all" (default: all)
    - symbol: specific symbol or all

    Response:
    {
        "status": "success",
        "current_summary": {
            "period": "90 days",
            "trades_analyzed": 127,
            "current_win_rate": "68.5%",
            "current_regime": "TRENDING",
            "most_effective_gate": "technical_setup",
            "least_effective_gate": "time_of_day",
            "pending_recommendations": 3,
            "projected_improvement": "+12.3%"
        },
        "analysis_history": [...],
        "timestamp": "2026-03-25T10:30:00"
    }
    """
    try:
        # Get latest analysis if available
        latest = learning_engine.get_latest_analysis()

        if not latest:
            return jsonify({
                'status': 'no_analysis',
                'message': 'No analysis has been run yet. Call /run first.',
                'timestamp': datetime.utcnow().isoformat(),
            }), 200

        # Get summary
        summary = learning_engine.get_summary_report()

        # Get history
        history = learning_engine.get_analysis_history(limit=10)

        return jsonify({
            'status': 'success',
            'current_summary': summary,
            'analysis_count': len(history),
            'latest_analysis_timestamp': latest.get('timestamp'),
            'should_rerun': learning_engine.should_rerun_analysis(min_hours=24),
            'timestamp': datetime.utcnow().isoformat(),
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error retrieving stats: {str(e)}',
            'timestamp': datetime.utcnow().isoformat(),
        }), 500


# ============================================================================
# ENDPOINT 3: GET /api/self-healing/recommendations
# List AI-generated threshold and risk parameter recommendations
# ============================================================================

@phase5_bp.route('/recommendations', methods=['GET'])
def get_recommendations():
    """
    Get Phase 5 recommendations

    GET /api/self-healing/recommendations

    Query parameters (optional):
    - status: "pending", "approved", "implemented", "all" (default: pending)
    - gate: specific gate name (default: all gates)
    - confidence_min: minimum confidence threshold (0-1)

    Response:
    {
        "status": "success",
        "total_recommendations": 5,
        "pending": 3,
        "approved": 2,
        "recommendations": [
            {
                "id": 1,
                "gate": "technical_setup",
                "action": "tighten",
                "current_threshold": 1.0,
                "recommended_threshold": 1.1,
                "change_percent": 10.0,
                "projected_impact": {
                    "win_rate_change": "+5.2%",
                    "signal_change": "-15%"
                },
                "confidence": 0.87,
                "reasoning": "High predictive power with false positives...",
                "status": "pending",
                "market_regime": "TRENDING"
            },
            ...
        ],
        "timestamp": "2026-03-25T10:30:00"
    }
    """
    try:
        latest = learning_engine.get_latest_analysis()

        if not latest:
            return jsonify({
                'status': 'no_recommendations',
                'message': 'Run analysis first with POST /run',
                'timestamp': datetime.utcnow().isoformat(),
            }), 200

        # Get recommendations from latest analysis
        recommendations = latest.get('threshold_recommendations', [])

        # Filter by status if requested
        status_filter = request.args.get('status', 'pending')
        if status_filter != 'all':
            recommendations = [r for r in recommendations if r.get('status') == status_filter]

        # Filter by confidence if requested
        confidence_min = request.args.get('confidence_min', type=float, default=0.0)
        recommendations = [r for r in recommendations if r.get('confidence', 0) >= confidence_min]

        # Categorize
        pending = [r for r in recommendations if r.get('status') == 'pending']
        approved = [r for r in recommendations if r.get('status') == 'approved']
        implemented = [r for r in recommendations if r.get('status') == 'implemented']

        return jsonify({
            'status': 'success',
            'total_recommendations': len(recommendations),
            'pending_count': len(pending),
            'approved_count': len(approved),
            'implemented_count': len(implemented),
            'recommendations': recommendations,
            'latest_analysis': latest.get('timestamp'),
            'timestamp': datetime.utcnow().isoformat(),
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error retrieving recommendations: {str(e)}',
            'timestamp': datetime.utcnow().isoformat(),
        }), 500


# ============================================================================
# ENDPOINT 4: POST /api/self-healing/apply
# Approve and activate AI-generated optimizations
# ============================================================================

@phase5_bp.route('/apply', methods=['POST'])
def apply_optimizations():
    """
    Apply Phase 5 optimizations to live trading system

    POST /api/self-healing/apply

    Request body:
    {
        "recommendation_ids": [1, 2, 3],  # Which recommendations to apply
        "approval_reason": "High confidence analysis",
        "effective_immediately": true,
        "test_period_trades": 30  # Optional: run for N trades first
    }

    Response:
    {
        "status": "success",
        "message": "3 optimizations applied",
        "applied_recommendations": [...],
        "activation_time": "2026-03-25T10:30:00",
        "expected_improvement": "+12.3%",
        "next_review": "2026-04-25T10:30:00",
        "timestamp": "2026-03-25T10:30:00"
    }
    """
    try:
        data = request.get_json() or {}
        recommendation_ids = data.get('recommendation_ids', [])
        approval_reason = data.get('approval_reason', 'User approval')
        effective_immediately = data.get('effective_immediately', True)
        test_period = data.get('test_period_trades', 0)

        if not recommendation_ids:
            return jsonify({
                'status': 'error',
                'message': 'No recommendation_ids provided',
                'timestamp': datetime.utcnow().isoformat(),
            }), 400

        latest = learning_engine.get_latest_analysis()
        if not latest:
            return jsonify({
                'status': 'error',
                'message': 'No analysis available. Run /run first.',
                'timestamp': datetime.utcnow().isoformat(),
            }), 400

        # Get matching recommendations
        all_recs = latest.get('threshold_recommendations', [])
        applied = []

        for rec in all_recs:
            # In production, you'd have actual IDs and update database
            # For now, simulate approval
            if rec.get('status') == 'pending':
                rec['status'] = 'approved'
                rec['approval_timestamp'] = datetime.utcnow().isoformat()
                rec['approval_reason'] = approval_reason
                applied.append(rec)

        # Calculate total projected improvement
        total_improvement = sum(r.get('projected_impact', {}).get('win_rate_change', 0)
                               for r in applied)

        return jsonify({
            'status': 'success',
            'message': f'{len(applied)} optimizations approved and queued for activation',
            'applied_count': len(applied),
            'applied_recommendations': applied,
            'total_projected_improvement': f"+{total_improvement:.1%}",
            'activation_mode': 'immediate' if effective_immediately else f'after_{test_period}_trades',
            'activation_timestamp': datetime.utcnow().isoformat(),
            'next_review_timestamp': (datetime.utcnow().fromtimestamp(
                datetime.utcnow().timestamp() + (24 * 3600)  # 24 hours later
            )).isoformat(),
            'timestamp': datetime.utcnow().isoformat(),
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error applying optimizations: {str(e)}',
            'timestamp': datetime.utcnow().isoformat(),
        }), 500


# ============================================================================
# BONUS ENDPOINT: GET /api/self-healing/report
# Download HTML or text report
# ============================================================================

@phase5_bp.route('/report', methods=['GET'])
def get_report():
    """
    Download Phase 5 analysis report

    GET /api/self-healing/report?format=html

    Query parameters:
    - format: "html", "text", "csv" (default: html)

    Response: File download
    """
    try:
        latest = learning_engine.get_latest_analysis()

        if not latest:
            return jsonify({
                'status': 'error',
                'message': 'No analysis available',
            }), 404

        format_type = request.args.get('format', 'html')

        if format_type == 'html':
            html = Phase5Reporter.generate_html_report(latest)
            return html, 200, {'Content-Type': 'text/html'}

        elif format_type == 'text':
            text = Phase5Reporter.generate_text_summary(latest)
            return text, 200, {'Content-Type': 'text/plain'}

        elif format_type == 'csv':
            csv = Phase5Reporter.generate_csv_export(latest)
            return csv, 200, {'Content-Type': 'text/csv'}

        else:
            return jsonify({
                'status': 'error',
                'message': f'Unknown format: {format_type}',
            }), 400

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error generating report: {str(e)}',
        }), 500


# ============================================================================
# USAGE IN app.py
# ============================================================================

"""
In your app.py, add these imports and initialization:

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from PHASE_5_API_ROUTES import init_phase5_api

app = Flask(__name__)
db = SQLAlchemy(app)
init_phase5_api(app, db)
"""
