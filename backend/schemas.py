from pydantic import BaseModel, Field
from typing import Optional, Any


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
    order_id: str = Field(..., description="Dhan order ID to sell")
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
