import sys
import os
import httpx
from mcp.server.fastmcp import FastMCP
from typing import Optional

BASE_URL = "http://localhost:8000"

mcp = FastMCP("Kotak Neo Trading Assistant")


def _call_api(method: str, path: str, params: dict = None, json: dict = None) -> dict:
    url = f"{BASE_URL}{path}"
    try:
        with httpx.Client(timeout=15.0) as client:
            if method.upper() == "GET":
                resp = client.get(url, params=params)
            else:
                resp = client.post(url, json=json)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        print(f"Error calling API {path}: {e}", file=sys.stderr)
        return {"success": False, "message": f"API Error: {str(e)}", "data": None}


@mcp.tool()
def get_market_overview() -> str:
    """Get the live NIFTY, BANKNIFTY prices and India VIX sentiment."""
    result = _call_api("GET", "/market")
    if not result.get("success"):
        return f"Error fetching market overview: {result.get('message')}"
    data = result.get("data", {})
    nifty = data.get("nifty", {})
    banknifty = data.get("banknifty", {})
    vix = data.get("india_vix", {})
    return (
        f"📊 **Market Overview**\n"
        f"- **NIFTY**: LTP: ₹{nifty.get('ltp')} | Open: {nifty.get('open')} | High: {nifty.get('high')} | Low: {nifty.get('low')}\n"
        f"- **BANKNIFTY**: LTP: ₹{banknifty.get('ltp')} | Open: {banknifty.get('open')} | High: {banknifty.get('high')} | Low: {banknifty.get('low')}\n"
        f"- **India VIX**: {vix.get('vix') or 'N/A'}"
    )


@mcp.tool()
def get_option_chain(symbol: str = "NIFTY") -> str:
    """Get the option chain for NIFTY or BANKNIFTY."""
    result = _call_api("GET", "/market/optionchain", params={"symbol": symbol})
    if not result.get("success"):
        return f"Error fetching option chain: {result.get('message')}"
    return str(result.get("data"))


@mcp.tool()
def get_market_analysis(symbol: str = "NIFTY") -> str:
    """Get the AI analysis (trend, confidence, signal, reasoning) for NIFTY or BANKNIFTY options."""
    result = _call_api("GET", "/market/analysis", params={"symbol": symbol})
    if not result.get("success"):
        return f"Error executing market analysis: {result.get('message')}"
    data = result.get("data", {})
    return (
        f"🧠 **AI Options Analysis ({symbol})**\n"
        f"- **Signal**: {data.get('signal')}\n"
        f"- **Trend**: {data.get('trend')}\n"
        f"- **Confidence**: {data.get('confidence')}%\n"
        f"- **Reasoning**: {data.get('reason')}"
    )


@mcp.tool()
def place_buy_order(
    symbol: str,
    strike: float,
    expiry: str,
    option_type: str,
    quantity: Optional[int] = None,
    stoploss: Optional[float] = None,
    target: Optional[float] = None,
    reason: Optional[str] = None,
) -> str:
    """Place a buy order for NIFTY or BANKNIFTY options.
    symbol: 'NIFTY' or 'BANKNIFTY'
    strike: Strike price (e.g. 24000)
    expiry: Expiry date (format: YYYY-MM-DD or exchange format)
    option_type: 'CALL' or 'PUT'
    quantity: Number of units (lot size multiple)
    stoploss: Optional trigger stoploss price
    target: Optional target target price
    reason: Optional reason for placing the trade
    """
    payload = {
        "symbol": symbol,
        "strike": strike,
        "expiry": expiry,
        "option_type": option_type,
        "quantity": quantity,
        "stoploss": stoploss,
        "target": target,
        "reason": reason,
    }
    result = _call_api("POST", "/trade/buy", json=payload)
    if not result.get("success"):
        return f"❌ Buy Order Failed: {result.get('message')}"
    data = result.get("data", {})
    return (
        f"✅ **Buy Order Placed Successfully**\n"
        f"- **Trade ID**: {data.get('trade_id')}\n"
        f"- **Order ID**: {data.get('order_id')}\n"
        f"- **Trading Symbol**: {data.get('trading_symbol')}"
    )


@mcp.tool()
def place_sell_order(order_id: str, exit_price: Optional[float] = None, reason: Optional[str] = None) -> str:
    """Place a sell order to exit or square off an order by order_id."""
    payload = {"order_id": order_id, "exit_price": exit_price, "reason": reason}
    result = _call_api("POST", "/trade/sell", json=payload)
    if not result.get("success"):
        return f"❌ Sell Order Failed: {result.get('message')}"
    return "✅ Sell order placed successfully."


@mcp.tool()
def exit_active_trade(trade_id: int, reason: Optional[str] = None) -> str:
    """Exit an open trade by its local trade_id and calculate final PnL."""
    payload = {"trade_id": trade_id, "reason": reason}
    result = _call_api("POST", "/trade/exit", json=payload)
    if not result.get("success"):
        return f"❌ Trade Exit Failed: {result.get('message')}"
    data = result.get("data", {})
    return f"✅ **Trade Exited Successfully**\n- **Trade ID**: {data.get('trade_id')}\n- **PnL**: ₹{data.get('pnl')}"


@mcp.tool()
def get_portfolio() -> str:
    """Get Kotak Neo portfolio holdings, open positions, and fund limits."""
    result = _call_api("GET", "/portfolio")
    if not result.get("success"):
        return f"Error fetching portfolio: {result.get('message')}"
    data = result.get("data", {})
    limits = data.get("limits", {})
    positions = data.get("positions", {})
    holdings = data.get("holdings", {})
    return (
        f"💼 **Portfolio Status**\n"
        f"- **Available Margin**: ₹{limits.get('Net', '0')}\n"
        f"- **Positions**: {positions.get('desc', 'No active positions') if isinstance(positions, dict) else len(positions)}\n"
        f"- **Holdings**: {holdings.get('desc', 'No holdings') if isinstance(holdings, dict) else len(holdings)}"
    )


@mcp.tool()
def get_orders() -> str:
    """Fetch all orders from the Kotak Neo order book for today."""
    result = _call_api("GET", "/trade/orders")
    if not result.get("success"):
        return f"Error fetching orders: {result.get('message')}"
    return str(result.get("data"))


@mcp.tool()
def get_positions() -> str:
    """Fetch active trading positions from Kotak Neo."""
    result = _call_api("GET", "/trade/positions")
    if not result.get("success"):
        return f"Error fetching positions: {result.get('message')}"
    return str(result.get("data"))


@mcp.tool()
def get_trade_history() -> str:
    """Get the local SQLite trade journal history of all closed and open trades."""
    result = _call_api("GET", "/trade/history")
    if not result.get("success"):
        return f"Error fetching trade history: {result.get('message')}"
    trades = result.get("data", [])
    if not trades:
        return "No trades recorded in journal yet."

    lines = ["📓 **Trade Journal History**"]
    for t in trades[:15]:
        lines.append(
            f"- [{t.get('timestamp')[:16]}] Trade #{t.get('id')} | {t.get('symbol')} {t.get('strike')} {t.get('option_type')} | Status: {t.get('status')} | PnL: ₹{t.get('pnl')}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_performance_analytics() -> str:
    """Get trade performance analytics, win rate, average win/loss, profit factor, and PnL."""
    result = _call_api("GET", "/analytics")
    if not result.get("success"):
        return f"Error fetching analytics: {result.get('message')}"
    d = result.get("data", {})
    return (
        f"📊 **Performance Analytics**\n"
        f"- **Total Trades**: {d.get('total_trades')} ({d.get('closed_trades')} closed, {d.get('open_trades')} open)\n"
        f"- **Win Rate**: {d.get('win_rate')}%\n"
        f"- **Total PnL**: ₹{d.get('total_pnl')}\n"
        f"- **Today's PnL**: ₹{d.get('today_pnl')}\n"
        f"- **Avg Win**: ₹{d.get('avg_win')} | **Avg Loss**: ₹{d.get('avg_loss')}\n"
        f"- **Profit Factor**: {d.get('profit_factor')}"
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
