from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


class TrendDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    SIDEWAYS = "SIDEWAYS"


class SignalType(str, Enum):
    BUY_CALL = "BUY_CALL"
    BUY_PUT = "BUY_PUT"
    NO_TRADE = "NO_TRADE"


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class MarketData(BaseModel):
    symbol: str
    ltp: float
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    timestamp: datetime = datetime.now()


class AnalysisResult(BaseModel):
    trend: TrendDirection
    confidence: float
    signal: SignalType
    reason: str


class StrategyRecommendation(BaseModel):
    action: SignalType
    symbol: str
    strike: float
    option_type: OptionType
    entry_price: float
    stoploss: float
    target: float
    quantity: int
    reason: str
    confidence: float


class RiskDecision(BaseModel):
    approved: bool
    reason: str
    risk_amount: float = 0.0
    risk_reward_ratio: float = 0.0


class Trade(BaseModel):
    id: Optional[int] = None
    timestamp: str
    symbol: str
    strike: Optional[float] = None
    expiry: Optional[str] = None
    option_type: Optional[str] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    quantity: int
    stoploss: Optional[float] = None
    target: Optional[float] = None
    pnl: float = 0.0
    strategy: Optional[str] = None
    reason: Optional[str] = None
    status: str = TradeStatus.OPEN
    order_id: Optional[str] = None
