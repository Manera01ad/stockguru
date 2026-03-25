"""
Phase 5 Visualization & Reporting

Generates charts, dashboards, and reports from Phase 5 analysis.
"""

from typing import Dict, List
from datetime import datetime


class Phase5Reporter:
    """
    Generates reports and visualizations for Phase 5 analysis
    """

    @staticmethod
    def generate_html_report(analysis_results: Dict) -> str:
        """
        Generate HTML report from analysis results

        Args:
            analysis_results: Output from LearningEngine.run_full_analysis()

        Returns:
            HTML string
        """
        if analysis_results.get("status") != "success":
            return "<h1>❌ Analysis Failed</h1><p>No data available</p>"

        metrics = analysis_results.get("optimization_metrics", {})
        regime = analysis_results.get("market_regime", {})
        recommendations = analysis_results.get("threshold_recommendations", [])
        risk_opt = analysis_results.get("risk_optimization", {})

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Phase 5 Analysis Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
                .section {{ background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
                .metric-value {{ font-size: 24px; font-weight: bold; color: #667eea; }}
                .metric-label {{ font-size: 12px; color: #666; }}
                .positive {{ color: #10b981; }}
                .negative {{ color: #ef4444; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
                th {{ background: #f3f4f6; font-weight: bold; }}
                .recommendation {{ background: #f0f9ff; padding: 15px; margin: 10px 0; border-left: 4px solid #3b82f6; border-radius: 4px; }}
                .status-pending {{ color: #f59e0b; }}
                .status-approved {{ color: #10b981; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🧠 Phase 5 Self-Healing Analysis Report</h1>
                <p>Generated: {analysis_results.get('timestamp', datetime.utcnow().isoformat())}</p>
            </div>

            <!-- Summary Metrics -->
            <div class="section">
                <h2>📊 Analysis Summary</h2>
                <div class="metric">
                    <div class="metric-label">Analysis Period</div>
                    <div class="metric-value">{analysis_results['analysis_period']['days']} days</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Trades Analyzed</div>
                    <div class="metric-value">{analysis_results['analysis_period']['trades_analyzed']}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Win Rate</div>
                    <div class="metric-value positive">{metrics.get('win_rate', 0):.1%}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Current Regime</div>
                    <div class="metric-value">{regime.get('current', 'UNKNOWN')}</div>
                </div>
            </div>

            <!-- Trade Outcomes -->
            <div class="section">
                <h2>📈 Trade Outcomes</h2>
                <table>
                    <tr>
                        <th>Metric</th>
                        <th>Value</th>
                    </tr>
                    <tr>
                        <td>Total Trades</td>
                        <td>{analysis_results['trade_outcomes'].get('total_trades', 0)}</td>
                    </tr>
                    <tr>
                        <td>Winning Trades</td>
                        <td class="positive">{analysis_results['trade_outcomes'].get('winning_trades', 0)}</td>
                    </tr>
                    <tr>
                        <td>Losing Trades</td>
                        <td class="negative">{analysis_results['trade_outcomes'].get('losing_trades', 0)}</td>
                    </tr>
                    <tr>
                        <td>Win Rate</td>
                        <td>{analysis_results['trade_outcomes'].get('win_rate', 0):.1%}</td>
                    </tr>
                    <tr>
                        <td>Profit Factor</td>
                        <td>{analysis_results['trade_outcomes'].get('profit_factor', 0):.2f}</td>
                    </tr>
                </table>
            </div>

            <!-- Market Regime Analysis -->
            <div class="section">
                <h2>🌍 Market Regime Analysis</h2>
                <p><strong>Current Regime:</strong> {regime.get('current', 'UNKNOWN')} (Confidence: {regime.get('confidence', 0):.0%})</p>
                <p><strong>Best Strategy:</strong> {regime.get('characteristics', {}).get('best_strategy', 'N/A')}</p>
                <p><strong>Suitable Gates:</strong> {', '.join(regime.get('characteristics', {}).get('suitable_gates', []))}</p>
                <p><strong>Typical Win Rate:</strong> {regime.get('characteristics', {}).get('typical_win_rate', 'N/A')}</p>
            </div>

            <!-- Gate Effectiveness -->
            <div class="section">
                <h2>🎯 Gate Effectiveness Analysis</h2>
                <p><strong>Most Effective:</strong> {metrics.get('most_effective_gate', 'N/A')}</p>
                <p><strong>Least Effective:</strong> {metrics.get('least_effective_gate', 'N/A')}</p>
                <p><strong>Gates Analyzed:</strong> {len(metrics.get('gate_effectiveness_scores', {}))}</p>
            </div>

            <!-- Threshold Recommendations -->
            <div class="section">
                <h2>💡 Threshold Recommendations ({len(recommendations)})</h2>
                {Phase5Reporter._generate_recommendations_html(recommendations)}
            </div>

            <!-- Risk Optimization -->
            <div class="section">
                <h2>⚠️ Risk Optimization</h2>
                <table>
                    <tr>
                        <th>Parameter</th>
                        <th>Optimized Value</th>
                    </tr>
                    <tr>
                        <td>Position Size</td>
                        <td>{risk_opt.get('position_size_percent', 0):.1%}</td>
                    </tr>
                    <tr>
                        <td>Stop Loss (ATR Multiple)</td>
                        <td>{risk_opt.get('stop_loss_atr_multiple', 0):.2f}x</td>
                    </tr>
                    <tr>
                        <td>Target R:R Ratio</td>
                        <td>1:{risk_opt.get('target_rr_ratio', 0):.2f}</td>
                    </tr>
                    <tr>
                        <td>Win Rate</td>
                        <td>{risk_opt.get('win_rate', 0):.1%}</td>
                    </tr>
                    <tr>
                        <td>Profit Factor</td>
                        <td>{risk_opt.get('profit_factor', 0):.2f}</td>
                    </tr>
                </table>
            </div>

            <!-- Next Actions -->
            <div class="section">
                <h2>🎯 Next Actions</h2>
                {Phase5Reporter._generate_next_actions_html(analysis_results.get('next_actions', []))}
            </div>

            <div style="text-align: center; margin-top: 40px; color: #999; font-size: 12px;">
                <p>StockGuru Phase 5 Self-Healing Strategy Layer</p>
                <p>This analysis is for educational purposes. Always consult with a financial advisor before trading.</p>
            </div>
        </body>
        </html>
        """

        return html

    @staticmethod
    def _generate_recommendations_html(recommendations: List[Dict]) -> str:
        """Generate HTML for recommendations"""
        if not recommendations:
            return "<p>No recommendations at this time.</p>"

        html = ""
        for rec in recommendations:
            change = rec.get('change_percent', 0)
            change_class = "positive" if change < 0 else "negative"

            html += f"""
            <div class="recommendation">
                <h4>{rec.get('gate', 'Unknown Gate')}</h4>
                <p><strong>Action:</strong> {'Tighten' if change > 0 else 'Relax'} threshold by {abs(change):.1f}%</p>
                <p><strong>Reasoning:</strong> {rec.get('reasoning', 'No reasoning provided')}</p>
                <p><strong>Projected Impact:</strong> Win-rate {'+' if rec.get('projected_impact', {}).get('win_rate_change', 0) > 0 else ''}{rec.get('projected_impact', {}).get('win_rate_change', 0):.1%}</p>
                <p><strong>Confidence:</strong> {rec.get('confidence', 0):.0%}</p>
                <p><strong>Status:</strong> <span class="status-{rec.get('status', 'pending')}">{rec.get('status', 'PENDING').upper()}</span></p>
            </div>
            """

        return html

    @staticmethod
    def _generate_next_actions_html(next_actions: List[Dict]) -> str:
        """Generate HTML for next actions"""
        if not next_actions:
            return "<p>No pending actions.</p>"

        html = ""
        for action in next_actions:
            html += f"""
            <div style="background: #f9fafb; padding: 15px; margin: 10px 0; border-radius: 4px; border-left: 4px solid #{'ef4444' if action.get('priority') == 'HIGH' else 'f59e0b'};")
                <p><strong>{action.get('action', 'Unknown Action')}</strong></p>
                <p style="margin: 5px 0; color: #666; font-size: 14px;">{action.get('details', '')}</p>
                <p style="margin: 5px 0; color: #666; font-size: 14px;"><strong>Expected Impact:</strong> {action.get('expected_impact', '')}</p>
                <p style="margin: 5px 0; color: #999; font-size: 12px;"><strong>Timeline:</strong> {action.get('timeline', '')}</p>
            </div>
            """

        return html

    @staticmethod
    def generate_text_summary(analysis_results: Dict) -> str:
        """
        Generate plain text summary

        Args:
            analysis_results: Analysis output

        Returns:
            Text summary
        """
        if analysis_results.get("status") != "success":
            return "❌ Analysis failed. No data available."

        metrics = analysis_results.get("optimization_metrics", {})
        regime = analysis_results.get("market_regime", {})
        recommendations = analysis_results.get("threshold_recommendations", [])

        text = f"""
╔════════════════════════════════════════════════════════════════╗
║         Phase 5 Self-Healing Strategy Analysis Summary         ║
╚════════════════════════════════════════════════════════════════╝

📊 ANALYSIS PERIOD
   Days Analyzed: {analysis_results['analysis_period']['days']}
   Trades Reviewed: {analysis_results['analysis_period']['trades_analyzed']}
   Date Range: {analysis_results['analysis_period']['start_date']} to {analysis_results['analysis_period']['end_date']}

📈 CURRENT PERFORMANCE
   Win Rate: {metrics.get('win_rate', 0):.1%}
   Total Trades: {analysis_results['trade_outcomes'].get('total_trades', 0)}
   Winning: {analysis_results['trade_outcomes'].get('winning_trades', 0)}
   Losing: {analysis_results['trade_outcomes'].get('losing_trades', 0)}

🌍 MARKET REGIME
   Current: {regime.get('current', 'UNKNOWN')} (Confidence: {regime.get('confidence', 0):.0%})
   Best Strategy: {regime.get('characteristics', {}).get('best_strategy', 'N/A')}
   Typical Win Rate: {regime.get('characteristics', {}).get('typical_win_rate', 'N/A')}

🎯 GATE ANALYSIS
   Total Gates: {len(metrics.get('gate_effectiveness_scores', {}))}
   Most Effective: {metrics.get('most_effective_gate', 'N/A')}
   Least Effective: {metrics.get('least_effective_gate', 'N/A')}

💡 RECOMMENDATIONS
   Pending: {len([r for r in recommendations if r.get('status') == 'pending'])}
   Approved: {len([r for r in recommendations if r.get('status') == 'approved'])}
   Total Impact: +{metrics.get('projected_improvement', 0):.1%} projected win-rate improvement

⚠️ RISK OPTIMIZATION
   Position Size: {analysis_results.get('risk_optimization', {}).get('position_size_percent', 0):.1%}
   Stop Loss: {analysis_results.get('risk_optimization', {}).get('stop_loss_atr_multiple', 0):.2f}x ATR
   Target R:R: 1:{analysis_results.get('risk_optimization', {}).get('target_rr_ratio', 0):.2f}

🎯 NEXT STEPS
   1. Review {len(recommendations)} pending recommendations
   2. Approve/reject threshold changes
   3. Monitor win-rate improvements over next 20-30 trades
   4. Re-run analysis in 24 hours

Generated: {analysis_results.get('timestamp', '')}
        """

        return text

    @staticmethod
    def generate_csv_export(analysis_results: Dict) -> str:
        """
        Generate CSV format for spreadsheet import

        Args:
            analysis_results: Analysis output

        Returns:
            CSV string
        """
        if analysis_results.get("status") != "success":
            return ""

        csv = "Gate,Action,Confidence,Win-Rate Impact,Signal Impact,Status\n"

        for rec in analysis_results.get("threshold_recommendations", []):
            csv += (
                f"{rec.get('gate', 'N/A')},"
                f"{'Tighten' if rec.get('change_percent', 0) > 0 else 'Relax'},"
                f"{rec.get('confidence', 0):.1%},"
                f"{rec.get('projected_impact', {}).get('win_rate_change', 0):+.1%},"
                f"{rec.get('projected_impact', {}).get('signal_change_percent', 0):+.1f}%,"
                f"{rec.get('status', 'pending').upper()}\n"
            )

        return csv
