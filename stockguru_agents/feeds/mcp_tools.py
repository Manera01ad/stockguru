"""
Claude API Tool Definitions for StockGuru Agents.

Agents that call Claude API can include these tool definitions so Claude
can request live market data mid-reasoning instead of relying on stale cache.

Usage in any agent:
    from stockguru_agents.feeds.mcp_tools import MARKET_TOOLS, handle_tool_call

    response = anthropic_client.messages.create(
        model="claude-opus-4-5-20251101",
        tools=MARKET_TOOLS,
        messages=[{"role":"user","content":"..."}]
    )
    result = handle_tool_call(response)   # auto-executes tool calls
"""

import json
import logging
from typing import List, Dict, Any

log = logging.getLogger("mcp_tools")

# ── Tool definitions for Claude API ───────────────────────────────────────────

MARKET_TOOLS: List[Dict] = [
    {
        "name": "get_live_price",
        "description": (
            "Get the current live price of an Indian stock, index, or crypto asset. "
            "Use this when you need an up-to-date price for signal confirmation, "
            "entry/exit calculations, or real-time analysis. "
            "Symbols: RELIANCE.NS (NSE equity), ^NSEI (Nifty 50), BTC-USD (crypto)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Yahoo Finance symbol, e.g. RELIANCE.NS, ^NSEI, HDFCBANK.NS, BTC-USD"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_live_orderbook",
        "description": (
            "Get the current live order book (bid/ask depth) for a symbol. "
            "Use this to check liquidity, bid-ask spread, and identify price walls "
            "before confirming a trade signal. Returns bids and asks with quantities."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Yahoo Finance symbol"},
                "depth":  {"type": "integer", "description": "Number of price levels each side (1-20)", "default": 5}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_recent_candles",
        "description": (
            "Get recent OHLCV candlestick data for technical analysis. "
            "Use this to check current trend, support/resistance, or EMA status. "
            "Keep interval and range short for real-time analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":   {"type": "string",  "description": "Yahoo Finance symbol"},
                "interval": {
                    "type": "string",
                    "description": "Candle timeframe",
                    "enum": ["1m","5m","15m","30m","60m","1h","1d","1wk"],
                    "default": "15m"
                },
                "range": {
                    "type": "string",
                    "description": "Data range",
                    "enum": ["1d","5d","1mo","3mo","6mo","1y"],
                    "default": "5d"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "check_market_status",
        "description": "Check if NSE, BSE, and MCX markets are currently open or closed.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "search_instrument",
        "description": (
            "Search for a stock symbol by company name or partial ticker. "
            "Use this when you have a company name but need the exact symbol."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Company name or partial ticker, e.g. 'Reliance', 'HDFC', 'bitcoin'"},
                "segment": {"type": "string", "description": "Filter: nse, bse, crypto, index, all", "default": "all"}
            },
            "required": ["query"]
        }
    }
]


# ── Tool executor ──────────────────────────────────────────────────────────────

def handle_tool_call(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """
    Execute a tool call from Claude and return the result as JSON string.
    Called when Claude's response contains a tool_use block.
    """
    try:
        from stockguru_agents.feeds import feed_manager

        if tool_name == "get_live_price":
            symbol = tool_input.get("symbol", "^NSEI")
            result = feed_manager.get_quote(symbol)
            result["symbol"] = symbol
            result["feed"]   = feed_manager.active_name
            return json.dumps(result, default=str)

        elif tool_name == "get_live_orderbook":
            symbol = tool_input.get("symbol", "^NSEI")
            depth  = int(tool_input.get("depth", 5))
            result = feed_manager.get_orderbook(symbol, depth)
            result["symbol"] = symbol
            result["feed"]   = feed_manager.active_name
            return json.dumps(result, default=str)

        elif tool_name == "get_recent_candles":
            symbol   = tool_input.get("symbol", "^NSEI")
            interval = tool_input.get("interval", "15m")
            range_   = tool_input.get("range",    "5d")
            result   = feed_manager.get_candles(symbol, interval, range_)
            # Truncate candles to avoid huge payloads
            if len(result.get("candles", [])) > 100:
                result["candles"] = result["candles"][-100:]
            result["feed"] = feed_manager.active_name
            return json.dumps(result, default=str)

        elif tool_name == "check_market_status":
            from stockguru_mcp_server import _market_status
            return json.dumps(_market_status(), default=str)

        elif tool_name == "search_instrument":
            query   = tool_input.get("query", "")
            segment = tool_input.get("segment", "all")
            try:
                from stockguru_agents.feeds.symbol_mapper import SymbolMapper
                mapper  = SymbolMapper()
                results = mapper.search(query, segment)
            except Exception:
                results = []
            return json.dumps({"results": results, "query": query}, default=str)

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        log.error(f"Tool call {tool_name} failed: {e}")
        return json.dumps({"error": str(e), "tool": tool_name})


def process_claude_response(response, messages: list, client, model: str,
                             max_tool_rounds: int = 3) -> str:
    """
    Full agentic loop: keep executing tool calls until Claude produces
    a final text response (no more tool_use blocks).

    Args:
        response:       Initial claude response object
        messages:       The messages list (will be mutated with tool results)
        client:         anthropic.Anthropic() client
        model:          Claude model string
        max_tool_rounds: Safety limit on tool call rounds

    Returns:
        Final text response from Claude
    """
    import anthropic

    for _ in range(max_tool_rounds):
        if response.stop_reason != "tool_use":
            break

        # Collect all tool uses in this response
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = handle_tool_call(block.name, block.input)
                tool_results.append({
                    "type":       "tool_result",
                    "tool_use_id": block.id,
                    "content":    result,
                })

        if not tool_results:
            break

        # Append assistant turn + tool results
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user",      "content": tool_results})

        # Continue the conversation
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            tools=MARKET_TOOLS,
            messages=messages,
        )

    # Extract final text
    for block in response.content:
        if hasattr(block, "text"):
            return block.text
    return ""
