from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from enum import Enum


# Enums
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


# Core Models
class MarketData(BaseModel):
    symbol: str
    ltp: float
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)


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


# Request / Response Schemas
class LoginRequest(BaseModel):
    totp: str = Field(..., description="6-digit Google Authenticator TOTP code")


class BuyRequest(BaseModel):
    symbol: str = Field(..., description="NIFTY or BANKNIFTY")
    strike: float = Field(..., description="Strike price")
    expiry: str = Field(..., description="Expiry date YYYY-MM-DD")
    option_type: str = Field(..., description="CALL or PUT")
    quantity: Optional[int] = Field(None, description="Lot quantity, uses default if not set")
    stoploss: Optional[float] = Field(None, description="Stop loss price")
    target: Optional[float] = Field(None, description="Target price")
    reason: Optional[str] = Field(None, description="Trade reason")


class SellRequest(BaseModel):
    order_id: str = Field(..., description="Order ID to sell")
    exit_price: Optional[float] = Field(None, description="Exit price for limit order")
    reason: Optional[str] = Field(None, description="Exit reason")


class ExitRequest(BaseModel):
    trade_id: int = Field(..., description="Internal trade ID to exit")
    reason: Optional[str] = Field(None, description="Exit reason")


class ModifySLRequest(BaseModel):
    order_id: str = Field(..., description="Order ID to modify")
    new_stoploss: float = Field(..., description="New stoploss price")


class CancelRequest(BaseModel):
    order_id: str = Field(..., description="Order ID to cancel")


class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None


class ChatRequest(BaseModel):
    message: str
