"""
broker_connector.py — StockGuru Full Broker Terminal Scaffold
═════════════════════════════════════════════════════════════
Implements NSE-grade broker terminal structures so StockGuru's paper
trading engine behaves exactly like a real broker terminal.

Architecture (plug-in design):
  ┌──────────────────────────────────────────┐
  │          BrokerInterface (ABC)            │  ← abstract contract
  └──────────────────────────────────────────┘
            ↑               ↑
  ┌─────────────────┐   ┌─────────────────────┐
  │  PaperBroker    │   │  LiveBroker (M4)     │
  │  (this file)    │   │  ZerodhaAdapter /    │
  │  simulates NSE  │   │  UpstoxAdapter /     │
  │  via yfinance   │   │  IIFLAdapter etc.    │
  └─────────────────┘   └─────────────────────┘

Order Flow (mirrors real terminal):
  place_order() → validate → risk_check → queue → execute → confirm
      ↓
  OrderBook (pending / open / complete / rejected / cancelled)
      ↓
  PositionBook (net qty, avg price, unrealised P&L, day P&L)
      ↓
  TradeBook  (fill history with exact costs)

NSE Order Types Supported:
  MARKET   — execute at LTP + slippage
  LIMIT    — execute only when LTP <= limit_price (BUY) or >= (SELL)
  SL       — stop-loss limit: trigger → place limit
  SL-M     — stop-loss market: trigger → execute at market
  AMO      — After Market Order (queued for next open)

Product Codes (NSE/BSE standard):
  CNC  — Cash and Carry (delivery equity, T+1 settlement)
  MIS  — Margin Intraday Square-off (auto exit at 3:15 PM)
  NRML — Normal (futures/options — for future use)

Validity Codes:
  DAY  — expires at end of session
  IOC  — Immediate or Cancel
  GTC  — Good Till Cancelled (simulated, requeued daily)

╔═══════════════════════════════════════════════════════════════╗
║  SAFETY INVARIANT                                             ║
║  LIVE_TRADING_ENABLED = False at module level.                ║
║  PaperBroker.execute() NEVER calls a real broker endpoint.    ║
║  LiveBroker requires a separate session confirmation token.   ║
╚═══════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import os
import json
import uuid
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, time as dtime
from enum import Enum
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("BrokerConnector")

# ══════════════════════════════════════════════════════════════════════════════
# 🔒 SAFETY LOCK
# ══════════════════════════════════════════════════════════════════════════════
LIVE_TRADING_ENABLED = False   # Never change this in this file

# ── NSE Market Hours ──────────────────────────────────────────────────────────
MARKET_OPEN    = dtime(9, 15)
MARKET_CLOSE   = dtime(15, 30)
PRE_OPEN_START = dtime(9,  0)
AMO_WINDOW     = dtime(15, 31)   # After Market Orders accepted after close

# ── Indian Equity Cost Model (matches Zerodha/Upstox/Angel One) ──────────────
SLIPPAGE_PCT       = 0.0005      # 0.05% slippage both sides
BROKERAGE_FLAT     = 20.0        # ₹20 per executed order (discount broker)
TRAILING_SL_PCT    = 0.03        # 3% trailing SL below highest price after T1
# ── Volatility Circuit Breaker ────────────────────────────────────────────────
VIX_CALM_THRESHOLD = 15.0        # VIX below this → normal 1-tick SL exit
VIX_HIGH_THRESHOLD = 20.0        # VIX above this → 2-tick confirmation required + trail widened
VIX_TRAIL_EXTRA_PER_10 = 0.01   # 1% extra trail width per 10 VIX pts above VIX_HIGH_THRESHOLD
VIX_TRAIL_MAX_EXTRA = 0.03      # Cap: never add more than 3% extra trail (= 6% total max)
SL_CONFIRM_TICKS_NORMAL = 1     # 1 consecutive tick below SL → exit (calm market)
SL_CONFIRM_TICKS_SPIKE  = 2     # 2 consecutive ticks below SL → exit (VIX elevated / spike)
STT_DELIVERY_PCT   = 0.001       # 0.1% Securities Transaction Tax — delivery both sides
STT_INTRADAY_PCT   = 0.00025     # 0.025% STT — intraday sell side only
EXCHANGE_CHARGE    = 0.0000297   # NSE transaction charge
SEBI_CHARGE        = 0.000001    # SEBI turnover fee
STAMP_DUTY_PCT     = 0.00015     # Stamp duty on BUY only
DP_CHARGES         = 15.93       # CDSL/NSDL depository charge per SELL (delivery)
GST_PCT            = 0.18        # GST on brokerage + exchange + SEBI


# ═════════════════════════════════════════════════════════════════════════════
# Enumerations — match NSE/BSE terminal codes exactly
# ═════════════════════════════════════════════════════════════════════════════

class OrderType(str, Enum):
    MARKET = "MARKET"    # Best available price
    LIMIT  = "LIMIT"     # Execute only at price or better
    SL     = "SL"        # Stop-Loss Limit (trigger → limit order)
    SL_M   = "SL-M"      # Stop-Loss Market (trigger → market order)
    AMO    = "AMO"        # After Market Order


class ProductCode(str, Enum):
    CNC  = "CNC"    # Delivery equity
    MIS  = "MIS"    # Intraday (auto-square at 3:15 PM)
    NRML = "NRML"   # Normal (F&O)


class Validity(str, Enum):
    DAY = "DAY"    # Valid for today's session
    IOC = "IOC"    # Immediate or Cancel
    GTC = "GTC"    # Good Till Cancelled (multi-day)


class TransactionType(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING   = "PENDING"    # Created, not yet submitted to exchange
    OPEN      = "OPEN"       # Submitted, waiting to match
    TRIGGERED = "TRIGGERED"  # SL trigger hit, limit/market placed
    COMPLETE  = "COMPLETE"   # Fully filled
    PARTIAL   = "PARTIAL"    # Partially filled
    CANCELLED = "CANCELLED"  # Cancelled by user or system
    REJECTED  = "REJECTED"   # Rejected (insufficient funds, risk breach, etc.)
    EXPIRED   = "EXPIRED"    # DAY order expired at session end


class Exchange(str, Enum):
    NSE = "NSE"
    BSE = "BSE"


# ═════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class CostBreakdown:
    """Complete Indian equity order cost breakdown."""
    brokerage:   float = 0.0
    stt:         float = 0.0
    exchange:    float = 0.0
    sebi:        float = 0.0
    stamp_duty:  float = 0.0
    dp_charges:  float = 0.0
    gst:         float = 0.0
    slippage:    float = 0.0
    total:       float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Order:
    """Single broker order — mirrors NSE terminal order object."""
    order_id:        str
    symbol:          str
    exchange:        Exchange
    transaction:     TransactionType
    order_type:      OrderType
    product:         ProductCode
    validity:        Validity
    quantity:        int
    price:           float              # limit price (0 for MARKET)
    trigger_price:   float              # for SL / SL-M
    disclosed_qty:   int                # iceberg qty (0 = full)

    # State
    status:          OrderStatus        = OrderStatus.PENDING
    filled_qty:      int                = 0
    avg_fill_price:  float              = 0.0
    pending_qty:     int                = 0
    cancelled_qty:   int                = 0

    # Metadata
    tag:             str                = ""    # algo tag / strategy id
    placed_at:       str                = ""
    updated_at:      str                = ""
    rejection_reason:str               = ""

    # Cost tracking
    costs:           Optional[dict]     = None
    total_value:     float              = 0.0   # filled_qty × avg_fill_price

    def __post_init__(self):
        self.pending_qty = self.quantity
        if not self.placed_at:
            self.placed_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.placed_at

    def to_dict(self) -> dict:
        d = asdict(self)
        # Convert enums to string values
        for k in ["exchange", "transaction", "order_type", "product",
                  "validity", "status"]:
            if k in d and hasattr(d[k], "value"):
                d[k] = d[k].value if isinstance(d[k], Enum) else d[k]
        return d


@dataclass
class Position:
    """Open or closed position — mirrors NSE terminal position object."""
    symbol:          str
    exchange:        Exchange
    product:         ProductCode
    quantity:        int                # net open qty (0 = closed)
    avg_price:       float              # average entry price
    last_price:      float              # last traded price
    realised_pnl:    float  = 0.0
    unrealised_pnl:  float  = 0.0
    day_pnl:         float  = 0.0
    day_pnl_pct:     float  = 0.0
    total_bought:    int    = 0
    total_sold:      int    = 0
    buy_value:       float  = 0.0
    sell_value:      float  = 0.0
    costs_incurred:  float  = 0.0
    target1:         float  = 0.0
    target2:         float  = 0.0
    stop_loss:       float  = 0.0
    trail_sl_high:   float  = 0.0       # Highest LTP seen after T1 (for trailing SL)
    sl_breach_ticks: int   = 0         # Consecutive ticks LTP ≤ stop_loss (circuit breaker)
    t1_booked:       bool   = False     # 50% booked at T1
    status:          str    = "OPEN"    # OPEN / CLOSED
    opened_at:       str    = ""
    closed_at:       str    = ""
    trade_ids:       List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ["exchange", "product"]:
            if k in d and hasattr(d[k], "value"):
                d[k] = d[k].value if isinstance(d[k], Enum) else d[k]
        return d


@dataclass
class Trade:
    """A completed fill — mirrors NSE trade book entry."""
    trade_id:        str
    order_id:        str
    symbol:          str
    exchange:        Exchange
    transaction:     TransactionType
    product:         ProductCode
    quantity:        int
    price:           float
    value:           float
    costs:           CostBreakdown
    net_value:       float              # value + costs (BUY) or value - costs (SELL)
    tag:             str    = ""
    executed_at:     str    = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ["exchange", "transaction", "product"]:
            if k in d and hasattr(d[k], "value"):
                d[k] = d[k].value if isinstance(d[k], Enum) else d[k]
        return d


@dataclass
class RiskCheck:
    """Pre-trade risk validation result."""
    passed:           bool
    rejection_reason: str               = ""
    margin_required:  float             = 0.0
    margin_available: float             = 0.0
    exposure_pct:     float             = 0.0   # % of capital in this trade
    checks: Dict[str, bool]             = field(default_factory=dict)

    @property
    def summary(self) -> str:
        if self.passed:
            return f"✅ Risk OK | Margin needed ₹{self.margin_required:,.0f}"
        return f"❌ Rejected: {self.rejection_reason}"


# ═════════════════════════════════════════════════════════════════════════════
# Cost Calculator
# ═════════════════════════════════════════════════════════════════════════════

def compute_costs(price: float, quantity: int,
                  transaction: TransactionType,
                  product: ProductCode) -> CostBreakdown:
    """
    Full Indian equity cost model.
    Delivery (CNC): STT on both BUY+SELL, DP charges on SELL
    Intraday (MIS): STT only on SELL side (lower rate)
    """
    value      = price * quantity
    slip       = value * SLIPPAGE_PCT
    brokerage  = min(BROKERAGE_FLAT, value * 0.0003)
    exchange   = value * EXCHANGE_CHARGE
    sebi       = value * SEBI_CHARGE
    gst        = (brokerage + exchange + sebi) * GST_PCT

    is_delivery = product == ProductCode.CNC
    is_buy      = transaction == TransactionType.BUY
    is_sell     = transaction == TransactionType.SELL

    stt = (value * STT_DELIVERY_PCT) if is_delivery else (
          (value * STT_INTRADAY_PCT) if is_sell else 0)

    stamp  = (value * STAMP_DUTY_PCT) if is_buy else 0
    dp     = DP_CHARGES if (is_sell and is_delivery) else 0

    total  = slip + brokerage + stt + exchange + sebi + stamp + dp + gst

    return CostBreakdown(
        brokerage  = round(brokerage, 2),
        stt        = round(stt,       2),
        exchange   = round(exchange + sebi, 2),
        sebi       = round(sebi,      2),
        stamp_duty = round(stamp,     2),
        dp_charges = round(dp,        2),
        gst        = round(gst,       2),
        slippage   = round(slip,      2),
        total      = round(total,     2),
    )


# ═════════════════════════════════════════════════════════════════════════════
# Abstract Broker Interface
# ═════════════════════════════════════════════════════════════════════════════

class BrokerInterface(ABC):
    """
    Abstract base class — every broker adapter must implement this interface.
    PaperBroker, ZerodhaAdapter, UpstoxAdapter, IIFLAdapter all derive from here.
    StockGuru's trade engine only ever talks to BrokerInterface — zero coupling.
    """

    @abstractmethod
    def place_order(
        self,
        symbol:       str,
        exchange:     Exchange,
        transaction:  TransactionType,
        order_type:   OrderType,
        product:      ProductCode,
        quantity:     int,
        price:        float         = 0.0,
        trigger_price:float         = 0.0,
        validity:     Validity      = Validity.DAY,
        tag:          str           = "",
        target1:      float         = 0.0,
        target2:      float         = 0.0,
        stop_loss:    float         = 0.0,
    ) -> Order:
        """Submit an order. Returns Order with assigned order_id."""

    @abstractmethod
    def modify_order(self, order_id: str, **kwargs) -> Order:
        """Modify price, qty, or trigger of a pending/open order."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> Order:
        """Cancel a pending or open order."""

    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Order]:
        """Fetch current state of an order by ID."""

    @abstractmethod
    def get_order_book(self) -> List[Order]:
        """Return all orders for this session."""

    @abstractmethod
    def get_position_book(self) -> List[Position]:
        """Return all open positions."""

    @abstractmethod
    def get_trade_book(self) -> List[Trade]:
        """Return all fills for this session."""

    @abstractmethod
    def get_margins(self) -> Dict[str, float]:
        """Return margin / fund details: available_cash, used_margin, total."""

    @abstractmethod
    def get_ltp(self, symbol: str, exchange: Exchange = Exchange.NSE) -> float:
        """Get last traded price (real-time for live, yfinance for paper)."""

    @abstractmethod
    def tick(self, price_cache: Dict[str, float]) -> List[Order]:
        """
        Called every 5 minutes with latest prices.
        Returns list of orders that changed status this tick
        (fills, SL triggers, T1/T2 exits, MIS auto-squares, expired orders).
        """

    def is_market_open(self) -> bool:
        now = datetime.now().time()
        return MARKET_OPEN <= now <= MARKET_CLOSE

    def is_amo_window(self) -> bool:
        """After Market Order window — post 3:30 PM."""
        return datetime.now().time() >= AMO_WINDOW


# ═════════════════════════════════════════════════════════════════════════════
# Paper Broker — Full NSE Simulation
# ═════════════════════════════════════════════════════════════════════════════

class PaperBroker(BrokerInterface):
    """
    Paper trading broker that behaves exactly like a real NSE terminal.

    Features:
    • All NSE order types: MARKET, LIMIT, SL, SL-M, AMO
    • All product codes: CNC (delivery), MIS (intraday), NRML (F&O)
    • Pre-trade risk checks: margin, position size, max single-trade exposure
    • Cost model: full Indian equity cost breakdown (brokerage, STT, exchange,
      SEBI, stamp duty, DP charges, GST, slippage)
    • T1/T2 target booking: 50% at T1, trail SL to breakeven, run T2
    • MIS auto-square: positions auto-closed at 3:15 PM if still open
    • SL monitoring: stop-loss triggers when LTP ≤ stop_loss
    • Order lifecycle: PENDING → OPEN → COMPLETE/REJECTED/CANCELLED/EXPIRED
    • Position book: realised + unrealised P&L, day P&L %
    • Trade book: every fill with itemised costs
    • Persistence: portfolio and trades saved as JSON after every action

    Risk Limits (configurable via .env):
    • MAX_SINGLE_TRADE_PCT    — max % of capital per trade (default 10%)
    • MAX_OPEN_POSITIONS      — max concurrent open positions (default 5)
    • MAX_DAILY_LOSS_PCT      — circuit-breaker: halt trading if day loss > N% (default 3%)
    • MIN_CONVICTION_GATES    — gates needed to auto-execute (default 6/8)
    """

    # ── Risk Config ───────────────────────────────────────────────────────────
    MAX_SINGLE_TRADE_PCT  = float(os.getenv("MAX_SINGLE_TRADE_PCT",  "0.10"))
    MAX_OPEN_POSITIONS    = int(os.getenv("MAX_OPEN_POSITIONS",     "5"))
    MAX_DAILY_LOSS_PCT    = float(os.getenv("MAX_DAILY_LOSS_PCT",    "3.0"))
    MIN_CONVICTION_GATES  = int(os.getenv("MIN_CONVICTION_GATES",   "6"))

    def __init__(self, portfolio_file: str, trades_file: str):
        self._portfolio_file = portfolio_file
        self._trades_file    = trades_file
        self._portfolio      = self._load_portfolio()
        self._trades         = self._load_trades()
        self._order_book:    Dict[str, Order]    = {}   # order_id → Order
        self._positions:     Dict[str, Position] = {}   # symbol → Position
        self._amo_queue:     List[Order]         = []   # AMO orders pending next open
        log.info("📊 PaperBroker initialised | Capital ₹%s | Cash ₹%s",
                 f"{self._portfolio['capital']:,.0f}",
                 f"{self._portfolio['available_cash']:,.0f}")

    # ─────────────────────────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────────────────────

    def _load_portfolio(self) -> dict:
        try:
            with open(self._portfolio_file) as f:
                return json.load(f)
        except Exception:
            return self._default_portfolio()

    def _default_portfolio(self) -> dict:
        cap = float(os.getenv("PAPER_CAPITAL", "500000"))
        return {
            "capital":          cap,
            "available_cash":   cap,
            "invested":         0.0,
            "unrealised_pnl":   0.0,
            "realised_pnl":     0.0,
            "total_pnl":        0.0,
            "total_return_pct": 0.0,
            "positions":        {},
            "daily_pnl":        {},
            "daily_pnl_pct":    0.0,
            "stats": {
                "total_trades":  0, "wins": 0, "losses": 0,
                "win_rate":      0.0, "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
                "best_trade":    None, "worst_trade": None,
                "max_drawdown":  0.0, "sharpe_approx": 0.0,
            },
            "safety":     {"live_trading": False, "mode": "PAPER_SIMULATION"},
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
        }

    def _save_portfolio(self):
        self._portfolio["last_updated"] = datetime.now().isoformat()
        os.makedirs(os.path.dirname(self._portfolio_file), exist_ok=True)
        with open(self._portfolio_file, "w") as f:
            json.dump(self._portfolio, f, indent=2, default=str)

    def _load_trades(self) -> List[dict]:
        try:
            with open(self._trades_file) as f:
                return json.load(f)
        except Exception:
            return []

    def _save_trades(self):
        os.makedirs(os.path.dirname(self._trades_file), exist_ok=True)
        with open(self._trades_file, "w") as f:
            json.dump(self._trades, f, indent=2, default=str)

    # ─────────────────────────────────────────────────────────────────────────
    # Risk Checks
    # ─────────────────────────────────────────────────────────────────────────

    def _risk_check(self, transaction: TransactionType, symbol: str,
                    quantity: int, price: float,
                    product: ProductCode) -> RiskCheck:
        """
        Pre-trade risk validation. All gates must pass for order acceptance.
        """
        costs      = compute_costs(price, quantity, transaction, product)
        trade_val  = price * quantity
        margin_req = trade_val + costs.total
        available  = self._portfolio["available_cash"]
        capital    = self._portfolio["capital"]
        checks     = {}

        # Gate 1: Sufficient funds
        checks["sufficient_funds"] = available >= margin_req
        if not checks["sufficient_funds"]:
            return RiskCheck(
                passed=False,
                rejection_reason=f"Insufficient funds: need ₹{margin_req:,.0f}, have ₹{available:,.0f}",
                margin_required=margin_req,
                margin_available=available,
                checks=checks,
            )

        # Gate 2: Single trade exposure limit
        exposure_pct = trade_val / capital
        checks["exposure_limit"] = exposure_pct <= self.MAX_SINGLE_TRADE_PCT
        if not checks["exposure_limit"]:
            return RiskCheck(
                passed=False,
                rejection_reason=(
                    f"Trade size {exposure_pct:.1%} exceeds max {self.MAX_SINGLE_TRADE_PCT:.0%} of capital. "
                    f"Reduce qty to {int(capital * self.MAX_SINGLE_TRADE_PCT / price)} shares."
                ),
                margin_required=margin_req,
                margin_available=available,
                exposure_pct=exposure_pct,
                checks=checks,
            )

        # Gate 3: Max open positions
        open_pos_count = len([p for p in self._positions.values()
                               if p.status == "OPEN" and p.quantity > 0])
        checks["position_limit"] = (
            transaction == TransactionType.SELL or
            open_pos_count < self.MAX_OPEN_POSITIONS
        )
        if not checks["position_limit"]:
            return RiskCheck(
                passed=False,
                rejection_reason=(
                    f"Max open positions ({self.MAX_OPEN_POSITIONS}) reached. "
                    f"Close a position before opening new ones."
                ),
                margin_required=margin_req,
                margin_available=available,
                checks=checks,
            )

        # Gate 4: Daily loss circuit breaker
        day_loss = self._portfolio.get("daily_pnl_pct", 0.0)
        checks["daily_loss_limit"] = day_loss > -self.MAX_DAILY_LOSS_PCT
        if not checks["daily_loss_limit"]:
            return RiskCheck(
                passed=False,
                rejection_reason=(
                    f"Daily loss circuit breaker: down {day_loss:.2f}%. "
                    f"Trading halted for today (limit: -{self.MAX_DAILY_LOSS_PCT}%)."
                ),
                checks=checks,
            )

        # Gate 5: No duplicate open position (for BUY)
        if transaction == TransactionType.BUY:
            checks["no_duplicate"] = symbol not in self._positions or \
                                     self._positions[symbol].status != "OPEN"
            if not checks["no_duplicate"]:
                # Allow adding to position — this is a pyramid check
                existing_qty = self._positions[symbol].quantity
                checks["no_duplicate"] = True   # Allow pyramiding for now

        return RiskCheck(
            passed=True,
            margin_required=margin_req,
            margin_available=available,
            exposure_pct=exposure_pct,
            checks={k: True for k in checks},  # all passed
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Order Placement
    # ─────────────────────────────────────────────────────────────────────────

    def place_order(
        self,
        symbol:       str,
        exchange:     Exchange       = Exchange.NSE,
        transaction:  TransactionType= TransactionType.BUY,
        order_type:   OrderType      = OrderType.MARKET,
        product:      ProductCode    = ProductCode.CNC,
        quantity:     int            = 0,
        price:        float          = 0.0,
        trigger_price:float          = 0.0,
        validity:     Validity       = Validity.DAY,
        tag:          str            = "",
        target1:      float          = 0.0,
        target2:      float          = 0.0,
        stop_loss:    float          = 0.0,
    ) -> Order:
        """
        Place an order. Validates → risk checks → queues in order book.
        Returns Order object (PENDING status until executed by tick()).
        """
        order_id = f"PB{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        # Basic validation
        if quantity <= 0:
            return self._reject_order(order_id, symbol, exchange, transaction,
                                      order_type, product, validity, quantity,
                                      price, trigger_price, tag,
                                      "Quantity must be > 0")

        if order_type == OrderType.LIMIT and price <= 0:
            return self._reject_order(order_id, symbol, exchange, transaction,
                                      order_type, product, validity, quantity,
                                      price, trigger_price, tag,
                                      "Limit price required for LIMIT order")

        if order_type in (OrderType.SL, OrderType.SL_M) and trigger_price <= 0:
            return self._reject_order(order_id, symbol, exchange, transaction,
                                      order_type, product, validity, quantity,
                                      price, trigger_price, tag,
                                      "Trigger price required for SL/SL-M order")

        # AMO handling
        if order_type == OrderType.AMO:
            order = self._make_order(order_id, symbol, exchange, transaction,
                                     order_type, product, validity, quantity,
                                     price, trigger_price, tag)
            order.status = OrderStatus.PENDING
            self._amo_queue.append(order)
            self._order_book[order_id] = order
            log.info("🕐 AMO queued | %s %d×%s", transaction.value, quantity, symbol)
            return order

        # Risk check (for BUY orders)
        if transaction == TransactionType.BUY:
            ltp = self._get_approx_price(symbol, price)
            check = self._risk_check(transaction, symbol, quantity, ltp, product)
            if not check.passed:
                log.warning("⛔ Risk rejected: %s | %s", symbol, check.rejection_reason)
                return self._reject_order(order_id, symbol, exchange, transaction,
                                          order_type, product, validity, quantity,
                                          price, trigger_price, tag,
                                          check.rejection_reason)

        order = self._make_order(order_id, symbol, exchange, transaction,
                                 order_type, product, validity, quantity,
                                 price, trigger_price, tag)
        order.status = OrderStatus.OPEN

        # Store target/SL in order tag for position management
        if target1 or target2 or stop_loss:
            order.tag = json.dumps({
                "base_tag": tag, "target1": target1,
                "target2": target2, "stop_loss": stop_loss,
            })

        self._order_book[order_id] = order

        # MARKET orders: execute immediately (no price constraint)
        if order_type == OrderType.MARKET:
            self._execute_order(order, self._get_approx_price(symbol, price))

        log.info("📋 Order placed | %s %s %d×%s @ %s [%s]",
                 order_type.value, transaction.value, quantity, symbol,
                 f"₹{price:.2f}" if price else "MARKET", order_id)
        return order

    # ─────────────────────────────────────────────────────────────────────────
    # Order Modification & Cancellation
    # ─────────────────────────────────────────────────────────────────────────

    def modify_order(self, order_id: str, **kwargs) -> Order:
        """Modify price, qty, or trigger of an OPEN order."""
        order = self._order_book.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        if order.status not in (OrderStatus.OPEN, OrderStatus.PENDING):
            raise ValueError(f"Cannot modify order in status {order.status.value}")

        for k, v in kwargs.items():
            if hasattr(order, k):
                setattr(order, k, v)
        order.updated_at = datetime.now().isoformat()
        log.info("✏️  Order modified | %s → %s", order_id, kwargs)
        return order

    def cancel_order(self, order_id: str) -> Order:
        """Cancel a PENDING or OPEN order."""
        order = self._order_book.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        if order.status not in (OrderStatus.OPEN, OrderStatus.PENDING):
            raise ValueError(f"Cannot cancel order in status {order.status.value}")

        order.status       = OrderStatus.CANCELLED
        order.cancelled_qty = order.pending_qty
        order.pending_qty  = 0
        order.updated_at   = datetime.now().isoformat()
        log.info("❌ Order cancelled | %s", order_id)
        return order

    # ─────────────────────────────────────────────────────────────────────────
    # Query Methods
    # ─────────────────────────────────────────────────────────────────────────

    def get_order(self, order_id: str) -> Optional[Order]:
        return self._order_book.get(order_id)

    def get_order_book(self) -> List[Order]:
        return list(self._order_book.values())

    def get_position_book(self) -> List[Position]:
        return list(self._positions.values())

    def get_trade_book(self) -> List[Trade]:
        # Reconstruct Trade objects from persisted dicts
        return self._trades  # stored as dicts for JSON serialisation

    def get_margins(self) -> Dict[str, float]:
        invested = sum(
            p.quantity * p.avg_price
            for p in self._positions.values()
            if p.status == "OPEN"
        )
        return {
            "available_cash":  self._portfolio["available_cash"],
            "invested":        invested,
            "unrealised_pnl":  self._portfolio.get("unrealised_pnl", 0),
            "total_capital":   self._portfolio["capital"],
            "used_margin":     invested,
        }

    def get_ltp(self, symbol: str, exchange: Exchange = Exchange.NSE) -> float:
        """Fetch last price via yfinance (paper trading only)."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            return float(ticker.fast_info.last_price)
        except Exception as e:
            log.warning("Could not fetch LTP for %s: %s", symbol, e)
            return 0.0

    def portfolio_snapshot(self) -> dict:
        """Return current portfolio state for shared_state."""
        p = self._portfolio
        return {
            "capital":          p["capital"],
            "available_cash":   p["available_cash"],
            "invested":         p.get("invested", 0),
            "unrealised_pnl":   p.get("unrealised_pnl", 0),
            "realised_pnl":     p.get("realised_pnl", 0),
            "total_pnl":        p.get("total_pnl", 0),
            "total_return_pct": p.get("total_return_pct", 0),
            "positions":        {k: v.to_dict() for k, v in self._positions.items()},
            "daily_pnl":        p.get("daily_pnl", {}),
            "daily_pnl_pct":    p.get("daily_pnl_pct", 0),
            "stats":            p.get("stats", {}),
            "open_orders":      len([o for o in self._order_book.values()
                                     if o.status == OrderStatus.OPEN]),
            "safety":           p.get("safety", {"live_trading": False}),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Tick Processing — called every 5 minutes with new prices
    # ─────────────────────────────────────────────────────────────────────────

    def tick(self, price_cache: Dict[str, float]) -> List[Order]:
        """
        Process one price tick. Handles:
        1. LIMIT order matching
        2. SL / SL-M trigger detection
        3. T1 / T2 target booking for open positions
        4. MIS auto-square at 3:15 PM
        5. DAY order expiry at session end
        6. AMO order submission at market open
        7. Position P&L update
        """
        changed: List[Order] = []
        now = datetime.now().time()

        # ── Submit AMO orders at market open ─────────────────────────────────
        if MARKET_OPEN <= now <= dtime(9, 17) and self._amo_queue:
            for order in self._amo_queue:
                order.status = OrderStatus.OPEN
                sym = order.symbol
                ltp = price_cache.get(sym, self.get_ltp(sym))
                if ltp > 0:
                    self._execute_order(order, ltp)
                    changed.append(order)
            self._amo_queue.clear()

        # ── MIS auto-square at 3:15 PM ────────────────────────────────────────
        if now >= dtime(15, 15):
            for sym, pos in list(self._positions.items()):
                if pos.product == ProductCode.MIS and pos.status == "OPEN" and pos.quantity > 0:
                    ltp = price_cache.get(sym, self.get_ltp(sym))
                    if ltp > 0:
                        log.info("⏰ MIS auto-square: %s @ ₹%.2f", sym, ltp)
                        sq_order = self.place_order(
                            symbol=sym, exchange=pos.exchange,
                            transaction=TransactionType.SELL,
                            order_type=OrderType.MARKET,
                            product=ProductCode.MIS,
                            quantity=pos.quantity,
                            tag="MIS_AUTO_SQUARE",
                        )
                        changed.append(sq_order)

        # ── DAY order expiry ──────────────────────────────────────────────────
        if now >= MARKET_CLOSE:
            for order in self._order_book.values():
                if (order.status == OrderStatus.OPEN
                        and order.validity == Validity.DAY):
                    order.status = OrderStatus.EXPIRED
                    order.updated_at = datetime.now().isoformat()
                    changed.append(order)
                    log.info("⌛ Order expired: %s", order.order_id)

        # ── Process open LIMIT / SL / SL-M orders ────────────────────────────
        for order in list(self._order_book.values()):
            if order.status != OrderStatus.OPEN:
                continue
            sym = order.symbol
            ltp = price_cache.get(sym, 0.0)
            if ltp <= 0:
                continue

            # LIMIT order matching
            if order.order_type == OrderType.LIMIT:
                should_fill = (
                    (order.transaction == TransactionType.BUY and ltp <= order.price) or
                    (order.transaction == TransactionType.SELL and ltp >= order.price)
                )
                if should_fill:
                    self._execute_order(order, ltp)
                    changed.append(order)

            # SL trigger detection
            elif order.order_type in (OrderType.SL, OrderType.SL_M):
                triggered = (
                    (order.transaction == TransactionType.SELL and ltp <= order.trigger_price) or
                    (order.transaction == TransactionType.BUY  and ltp >= order.trigger_price)
                )
                if triggered:
                    order.status = OrderStatus.TRIGGERED
                    log.info("🔔 SL triggered: %s @ ₹%.2f (trigger=₹%.2f)",
                             sym, ltp, order.trigger_price)
                    exec_price = order.price if order.order_type == OrderType.SL else ltp
                    self._execute_order(order, exec_price)
                    changed.append(order)

        # ── Volatility Circuit Breaker: read India VIX once per tick ─────────
        vix_entry = price_cache.get("INDIA VIX", {})
        vix_level = (
            vix_entry.get("price") if isinstance(vix_entry, dict) else vix_entry
        ) or 0.0
        # Effective trail PCT widens when VIX is elevated (max +VIX_TRAIL_MAX_EXTRA)
        vix_extra_trail = 0.0
        if vix_level > VIX_HIGH_THRESHOLD:
            vix_extra_trail = min(
                VIX_TRAIL_MAX_EXTRA,
                ((vix_level - VIX_HIGH_THRESHOLD) / 10.0) * VIX_TRAIL_EXTRA_PER_10,
            )
        effective_trail_pct = TRAILING_SL_PCT + vix_extra_trail
        # SL confirmation ticks: require 2 consecutive ticks when VIX is elevated
        sl_confirm_required = (
            SL_CONFIRM_TICKS_SPIKE if vix_level >= VIX_CALM_THRESHOLD
            else SL_CONFIRM_TICKS_NORMAL
        )

        # ── Target / Stop-Loss monitoring for open positions ─────────────────
        for sym, pos in list(self._positions.items()):
            if pos.status != "OPEN" or pos.quantity <= 0:
                continue
            ltp = price_cache.get(sym, 0.0)
            if ltp <= 0:
                continue

            pos.last_price    = ltp
            pos.unrealised_pnl = round(
                (ltp - pos.avg_price) * pos.quantity - pos.costs_incurred, 2
            )

            # T1 target booking (50%)
            if not pos.t1_booked and pos.target1 > 0 and ltp >= pos.target1:
                half_qty = max(1, pos.quantity // 2)
                log.info("🎯 T1 hit: %s @ ₹%.2f | booking %d shares", sym, ltp, half_qty)
                self.place_order(
                    symbol=sym, exchange=pos.exchange,
                    transaction=TransactionType.SELL,
                    order_type=OrderType.MARKET,
                    product=pos.product, quantity=half_qty,
                    tag="T1_BOOKING",
                )
                pos.t1_booked = True
                # Seed trailing SL: breakeven + start tracking high
                pos.trail_sl_high = ltp
                pos.stop_loss = pos.avg_price   # floor = breakeven
                pos.sl_breach_ticks = 0         # reset circuit-breaker counter
                log.info("🔒 TrailSL seeded: %s SL=₹%.2f (breakeven), high=₹%.2f",
                         sym, pos.stop_loss, pos.trail_sl_high)
                changed.append(self._order_book[list(self._order_book.keys())[-1]])

            # Trailing SL update — every tick after T1, ratchet SL upward
            # Uses VIX-aware effective_trail_pct so SL is wider in volatile markets
            elif pos.t1_booked and pos.quantity > 0:
                if ltp > pos.trail_sl_high:
                    pos.trail_sl_high = ltp
                    new_sl = round(
                        max(pos.avg_price, pos.trail_sl_high * (1 - effective_trail_pct)), 2
                    )
                    if new_sl > pos.stop_loss:
                        log.debug("📈 TrailSL raised: %s ₹%.2f → ₹%.2f (high=₹%.2f, trail=%.2f%%)",
                                  sym, pos.stop_loss, new_sl, pos.trail_sl_high,
                                  effective_trail_pct * 100)
                        pos.stop_loss = new_sl

            # T2 full exit
            if pos.t1_booked and pos.target2 > 0 and ltp >= pos.target2:
                log.info("🎯 T2 hit: %s @ ₹%.2f | full exit", sym, ltp)
                self.place_order(
                    symbol=sym, exchange=pos.exchange,
                    transaction=TransactionType.SELL,
                    order_type=OrderType.MARKET,
                    product=pos.product, quantity=pos.quantity,
                    tag="T2_EXIT",
                )
                changed.append(self._order_book[list(self._order_book.keys())[-1]])

            # Stop-loss exit — with volatility circuit breaker (N-tick confirmation)
            elif pos.stop_loss > 0 and ltp <= pos.stop_loss:
                pos.sl_breach_ticks += 1
                if pos.sl_breach_ticks >= sl_confirm_required:
                    log.info("🛑 SL confirmed: %s @ ₹%.2f (SL=₹%.2f, VIX=%.1f, "
                             "breachTicks=%d/%d)",
                             sym, ltp, pos.stop_loss, vix_level,
                             pos.sl_breach_ticks, sl_confirm_required)
                    self.place_order(
                        symbol=sym, exchange=pos.exchange,
                        transaction=TransactionType.SELL,
                        order_type=OrderType.MARKET,
                        product=pos.product, quantity=pos.quantity,
                        tag="SL_EXIT",
                    )
                    changed.append(self._order_book[list(self._order_book.keys())[-1]])
                else:
                    log.debug("⏳ SL breach tick %d/%d for %s @ ₹%.2f — waiting for confirmation",
                              pos.sl_breach_ticks, sl_confirm_required, sym, ltp)
            else:
                # Price recovered above SL — reset confirmation counter
                if pos.sl_breach_ticks > 0:
                    log.debug("✅ SL breach counter reset for %s (price recovered)", sym)
                pos.sl_breach_ticks = 0

        # ── Update portfolio aggregate P&L ────────────────────────────────────
        self._update_portfolio_pnl(price_cache)
        self._save_portfolio()

        return changed

    # ─────────────────────────────────────────────────────────────────────────
    # Internal Execution
    # ─────────────────────────────────────────────────────────────────────────

    def _execute_order(self, order: Order, exec_price: float):
        """Fill an order at exec_price. Updates position book and portfolio."""
        # Apply slippage
        if order.transaction == TransactionType.BUY:
            fill_price = round(exec_price * (1 + SLIPPAGE_PCT), 2)
        else:
            fill_price = round(exec_price * (1 - SLIPPAGE_PCT), 2)

        costs = compute_costs(fill_price, order.quantity,
                              order.transaction, order.product)
        fill_value = fill_price * order.quantity

        # Update order
        order.status        = OrderStatus.COMPLETE
        order.filled_qty    = order.quantity
        order.pending_qty   = 0
        order.avg_fill_price = fill_price
        order.total_value   = fill_value
        order.costs         = costs.as_dict()
        order.updated_at    = datetime.now().isoformat()

        # Create trade record
        trade_id = f"T{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        trade = {
            "trade_id":    trade_id,
            "order_id":    order.order_id,
            "symbol":      order.symbol,
            "exchange":    order.exchange.value if isinstance(order.exchange, Enum) else order.exchange,
            "transaction": order.transaction.value if isinstance(order.transaction, Enum) else order.transaction,
            "product":     order.product.value if isinstance(order.product, Enum) else order.product,
            "quantity":    order.quantity,
            "price":       fill_price,
            "value":       fill_value,
            "costs":       costs.as_dict(),
            "net_value":   round(fill_value + costs.total, 2)
                           if order.transaction == TransactionType.BUY
                           else round(fill_value - costs.total, 2),
            "tag":         order.tag,
            "executed_at": datetime.now().isoformat(),
        }
        self._trades.append(trade)
        self._save_trades()

        # Update positions
        self._update_position(order, fill_price, costs)

        # Update cash
        if order.transaction == TransactionType.BUY:
            debit = fill_value + costs.total
            self._portfolio["available_cash"] = round(
                self._portfolio["available_cash"] - debit, 2)
            self._portfolio["invested"] = round(
                self._portfolio.get("invested", 0) + fill_value, 2)
        else:
            credit = fill_value - costs.total
            self._portfolio["available_cash"] = round(
                self._portfolio["available_cash"] + credit, 2)
            self._portfolio["invested"] = round(
                max(0, self._portfolio.get("invested", 0) - fill_value), 2)

        log.info("✅ Filled | %s %s %d×%s @ ₹%.2f | Costs ₹%.2f | Net ₹%.2f",
                 order.transaction.value if isinstance(order.transaction, Enum) else order.transaction,
                 order.symbol, order.quantity, order.symbol,
                 fill_price, costs.total, trade["net_value"])

    def _update_position(self, order: Order, fill_price: float, costs: CostBreakdown):
        """Update position book after a fill."""
        sym = order.symbol
        is_buy = order.transaction == TransactionType.BUY

        if sym not in self._positions:
            self._positions[sym] = Position(
                symbol    = sym,
                exchange  = order.exchange,
                product   = order.product,
                quantity  = 0,
                avg_price = 0.0,
                last_price = fill_price,
                opened_at  = datetime.now().isoformat(),
            )

        pos = self._positions[sym]

        # Parse targets from order tag
        try:
            tag_data = json.loads(order.tag) if order.tag else {}
        except Exception:
            tag_data = {}
        if tag_data.get("target1"):   pos.target1   = tag_data["target1"]
        if tag_data.get("target2"):   pos.target2   = tag_data["target2"]
        if tag_data.get("stop_loss"): pos.stop_loss = tag_data["stop_loss"]

        if is_buy:
            # Weighted average entry price
            total_qty    = pos.quantity + order.quantity
            if total_qty > 0:
                pos.avg_price = round(
                    (pos.avg_price * pos.quantity + fill_price * order.quantity) / total_qty, 2
                )
            pos.quantity     += order.quantity
            pos.total_bought += order.quantity
            pos.buy_value    = round(pos.buy_value + fill_price * order.quantity, 2)
            pos.costs_incurred = round(pos.costs_incurred + costs.total, 2)
            pos.status        = "OPEN"
            if order.order_id:
                pos.trade_ids.append(order.order_id)

        else:  # SELL
            sell_value = fill_price * order.quantity
            cost_basis = pos.avg_price * order.quantity
            realised   = round(sell_value - cost_basis - costs.total, 2)
            pos.realised_pnl = round(pos.realised_pnl + realised, 2)
            pos.quantity     -= order.quantity
            pos.total_sold   += order.quantity
            pos.sell_value   = round(pos.sell_value + sell_value, 2)
            pos.costs_incurred = round(pos.costs_incurred + costs.total, 2)

            # Accumulate to portfolio realised P&L
            self._portfolio["realised_pnl"] = round(
                self._portfolio.get("realised_pnl", 0) + realised, 2
            )

            # Update stats
            stats = self._portfolio["stats"]
            stats["total_trades"] += 1
            if realised >= 0:
                stats["wins"]  += 1
                old_avg = stats.get("avg_win_pct", 0)
                pct = (realised / cost_basis) * 100 if cost_basis else 0
                stats["avg_win_pct"] = round(
                    (old_avg * (stats["wins"] - 1) + pct) / stats["wins"], 2
                )
                if stats["best_trade"] is None or pct > stats["best_trade"]:
                    stats["best_trade"] = round(pct, 2)
            else:
                stats["losses"] += 1
                old_avg = stats.get("avg_loss_pct", 0)
                pct = (realised / cost_basis) * 100 if cost_basis else 0
                stats["avg_loss_pct"] = round(
                    (old_avg * (stats["losses"] - 1) + pct) / stats["losses"], 2
                )
                if stats["worst_trade"] is None or pct < stats["worst_trade"]:
                    stats["worst_trade"] = round(pct, 2)
            total = stats["wins"] + stats["losses"]
            stats["win_rate"] = round(stats["wins"] / total, 4) if total else 0.0

            if pos.quantity <= 0:
                pos.quantity   = 0
                pos.status     = "CLOSED"
                pos.closed_at  = datetime.now().isoformat()

            pos.last_price = fill_price

        # Persist updated positions into portfolio dict
        self._portfolio["positions"][sym] = pos.to_dict()

    def _update_portfolio_pnl(self, price_cache: Dict[str, float]):
        """Recalculate unrealised P&L and total return from current prices."""
        total_unrealised = 0.0
        for sym, pos in self._positions.items():
            if pos.status != "OPEN" or pos.quantity <= 0:
                continue
            ltp = price_cache.get(sym, pos.last_price)
            pos.last_price      = ltp
            pos.unrealised_pnl  = round(
                (ltp - pos.avg_price) * pos.quantity - pos.costs_incurred * 0.5, 2
            )
            total_unrealised += pos.unrealised_pnl
            self._portfolio["positions"][sym] = pos.to_dict()

        cap = self._portfolio["capital"]
        realised = self._portfolio.get("realised_pnl", 0)
        self._portfolio["unrealised_pnl"]   = round(total_unrealised, 2)
        self._portfolio["total_pnl"]        = round(realised + total_unrealised, 2)
        self._portfolio["total_return_pct"] = round(
            (self._portfolio["total_pnl"] / cap) * 100 if cap else 0, 2
        )

        today = date.today().isoformat()
        self._portfolio["daily_pnl"][today] = self._portfolio["total_return_pct"]
        self._portfolio["daily_pnl_pct"]    = self._portfolio["total_return_pct"]

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _make_order(self, order_id, symbol, exchange, transaction, order_type,
                    product, validity, quantity, price, trigger_price, tag) -> Order:
        return Order(
            order_id      = order_id,
            symbol        = symbol,
            exchange      = exchange,
            transaction   = transaction,
            order_type    = order_type,
            product       = product,
            validity      = validity,
            quantity      = quantity,
            price         = price,
            trigger_price = trigger_price,
            disclosed_qty = 0,
            tag           = tag,
        )

    def _reject_order(self, order_id, symbol, exchange, transaction, order_type,
                      product, validity, quantity, price, trigger_price, tag,
                      reason) -> Order:
        order = self._make_order(order_id, symbol, exchange, transaction,
                                 order_type, product, validity, quantity,
                                 price, trigger_price, tag)
        order.status           = OrderStatus.REJECTED
        order.rejection_reason = reason
        order.pending_qty      = 0
        self._order_book[order_id] = order
        log.warning("🚫 Order rejected | %s: %s", symbol, reason)
        return order

    def _get_approx_price(self, symbol: str, hint_price: float = 0.0) -> float:
        """Return hint_price if given, else fetch via yfinance."""
        if hint_price > 0:
            return hint_price
        return self.get_ltp(symbol)


# ═════════════════════════════════════════════════════════════════════════════
# Factory — called by paper_trader.py and future live adapters
# ═════════════════════════════════════════════════════════════════════════════

def get_broker(portfolio_file: str, trades_file: str,
               live: bool = False) -> BrokerInterface:
    """
    Factory function. Always returns PaperBroker while LIVE_TRADING_ENABLED=False.
    In M4, when live trading is unlocked, this will return the appropriate
    LiveBroker adapter (Zerodha / Upstox / IIFL) based on .env config.
    """
    if live and LIVE_TRADING_ENABLED:
        raise RuntimeError(
            "Live trading not implemented. "
            "Set up a LiveBroker adapter in M4 and get explicit user confirmation."
        )
    return PaperBroker(portfolio_file=portfolio_file, trades_file=trades_file)


# ═════════════════════════════════════════════════════════════════════════════
# Convenience: Order Builder (fluent API for algo signal → order)
# ═════════════════════════════════════════════════════════════════════════════

class OrderBuilder:
    """
    Fluent builder so trade_signal.py can create orders without knowing
    broker internals. Converts StockGuru trade signal dicts to broker orders.

    Usage:
        order = (OrderBuilder(broker)
                    .from_signal(signal_dict)
                    .with_product(ProductCode.CNC)
                    .build())
    """

    def __init__(self, broker: BrokerInterface):
        self._broker   = broker
        self._symbol   = ""
        self._exchange = Exchange.NSE
        self._tx       = TransactionType.BUY
        self._type     = OrderType.MARKET
        self._product  = ProductCode.CNC
        self._validity = Validity.DAY
        self._qty      = 0
        self._price    = 0.0
        self._trigger  = 0.0
        self._tag      = ""
        self._t1       = 0.0
        self._t2       = 0.0
        self._sl       = 0.0

    def from_signal(self, signal: dict) -> "OrderBuilder":
        """Populate from a StockGuru trade signal dict."""
        sym = signal.get("symbol", "")
        # Strip exchange suffix for broker (NSE auto-appended)
        self._symbol = sym.replace(".NS", "").replace(".BO", "")
        self._exchange = Exchange.BSE if ".BO" in sym else Exchange.NSE
        self._tx    = (TransactionType.BUY
                       if signal.get("action", "BUY").upper() == "BUY"
                       else TransactionType.SELL)
        self._t1   = float(signal.get("target1", 0))
        self._t2   = float(signal.get("target2", 0))
        self._sl   = float(signal.get("stop_loss", 0))
        self._tag  = f"StockGuru|{signal.get('symbol','')}"
        return self

    def with_quantity_from_capital(self, capital: float, price: float,
                                   pct: float = 0.10) -> "OrderBuilder":
        """Auto-size position: invest `pct` of capital at `price`."""
        alloc = capital * pct
        self._qty   = max(1, int(alloc / price))
        self._price = price
        return self

    def with_product(self, product: ProductCode) -> "OrderBuilder":
        self._product = product
        return self

    def with_order_type(self, order_type: OrderType,
                        price: float = 0.0,
                        trigger: float = 0.0) -> "OrderBuilder":
        self._type    = order_type
        self._price   = price
        self._trigger = trigger
        return self

    def with_validity(self, validity: Validity) -> "OrderBuilder":
        self._validity = validity
        return self

    def build(self) -> Order:
        """Submit the order to the broker and return the Order object."""
        return self._broker.place_order(
            symbol        = self._symbol,
            exchange      = self._exchange,
            transaction   = self._tx,
            order_type    = self._type,
            product       = self._product,
            quantity      = self._qty,
            price         = self._price,
            trigger_price = self._trigger,
            validity      = self._validity,
            tag           = self._tag,
            target1       = self._t1,
            target2       = self._t2,
            stop_loss     = self._sl,
        )
