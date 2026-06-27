import sys
import os
import time
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database import init_db, get_all_trades, get_daily_pnl
from logger import setup_logger
from schemas import (
    LoginRequest, APIResponse, ChatRequest,
    BuyRequest, ExitRequest, SignalType
)
from services.kotak_service import get_kotak_service
from services.autotrade_service import get_autotrade_service, TradeService, LLMService, StrategyService, RiskService

logger = setup_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Options Trader")
    init_db()
    # Initialize services on startup
    get_kotak_service()
    get_autotrade_service()
    logger.info("Database and services ready")
    yield
    logger.info("Shutting down AI Options Trader")


app = FastAPI(
    title="AI Options Trader",
    description="NIFTY & BANKNIFTY Options Trading Assistant powered by Kotak Neo MCP",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    logger.info(f"-> {request.method} {request.url.path}")
    response = await call_next(request)
    duration = round((time.time() - start) * 1000, 2)
    logger.info(f"<- {request.method} {request.url.path} [{response.status_code}] {duration}ms")
    return response


# --- Authentication Endpoint ---
@app.post("/login", response_model=APIResponse, tags=["Authentication"])
def login(request: LoginRequest):
    try:
        kotak = get_kotak_service()
        res = kotak.login(totp=request.totp)
        return APIResponse(success=True, message="Authenticated with Kotak Neo", data=res)
    except Exception as e:
        logger.error(f"Login endpoint failed: {e}")
        return APIResponse(success=False, message=str(e))


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy"}


# --- Market Endpoints ---
@app.get("/market", response_model=APIResponse, tags=["Market"])
def get_market_overview():
    try:
        kotak = get_kotak_service()
        if not kotak.is_authenticated:
            return APIResponse(success=False, message="Not authenticated")
        overview = kotak.get_market_overview()
        return APIResponse(success=True, message="Market overview fetched", data=overview)
    except Exception as e:
        logger.error(f"Market overview failed: {e}")
        return APIResponse(success=False, message=str(e))


@app.get("/market/optionchain", response_model=APIResponse, tags=["Market"])
def get_option_chain(symbol: str = "NIFTY", expiry: str = ""):
    try:
        kotak = get_kotak_service()
        if not kotak.is_authenticated:
            return APIResponse(success=False, message="Not authenticated")
        chain = kotak.get_option_chain(symbol, expiry)
        return APIResponse(success=True, message="Option chain fetched", data=chain)
    except Exception as e:
        logger.error(f"Option chain fetch failed: {e}")
        return APIResponse(success=False, message=str(e))


# --- Trade Endpoints ---
@app.post("/trade/buy", response_model=APIResponse, tags=["Trade"])
def place_buy_order(request: BuyRequest):
    try:
        kotak = get_kotak_service()
        if not kotak.is_authenticated:
            return APIResponse(success=False, message="Not authenticated")
        trade_service = TradeService(kotak)
        res = trade_service.buy(request)
        return APIResponse(success=True, message="Buy order placed successfully", data=res)
    except Exception as e:
        logger.error(f"Buy order failed: {e}")
        return APIResponse(success=False, message=str(e))


@app.post("/trade/exit", response_model=APIResponse, tags=["Trade"])
def exit_open_trade(request: ExitRequest):
    try:
        kotak = get_kotak_service()
        if not kotak.is_authenticated:
            return APIResponse(success=False, message="Not authenticated")
        trade_service = TradeService(kotak)
        res = trade_service.exit_trade(request)
        return APIResponse(success=True, message="Trade exited successfully", data=res)
    except Exception as e:
        logger.error(f"Exit trade failed: {e}")
        return APIResponse(success=False, message=str(e))


@app.get("/trade/history", response_model=APIResponse, tags=["Trade"])
def get_trade_history(limit: int = 100):
    try:
        kotak = get_kotak_service()
        trade_service = TradeService(kotak)
        history = trade_service.get_history(limit)
        return APIResponse(success=True, message="Trade history fetched", data=history)
    except Exception as e:
        logger.error(f"Trade history fetch failed: {e}")
        return APIResponse(success=False, message=str(e))


# --- Portfolio Endpoint ---
@app.get("/portfolio", response_model=APIResponse, tags=["Portfolio"])
def get_portfolio():
    try:
        kotak = get_kotak_service()
        if not kotak.is_authenticated:
            return APIResponse(success=False, message="Not authenticated")
        positions = kotak.get_positions().get("data", [])
        holdings = kotak.get_holdings().get("data", [])
        limits = kotak.get_limits()
        available_margin = limits.get("Net", limits.get("data", {}).get("Net", "0.00"))
        
        return APIResponse(
            success=True,
            message="Portfolio details fetched",
            data={
                "positions": positions,
                "holdings": holdings,
                "margin": {"available_margin": available_margin}
            }
        )
    except Exception as e:
        logger.error(f"Portfolio fetch failed: {e}")
        return APIResponse(success=False, message=str(e))


# --- Analytics Endpoints ---
@app.get("/analytics", response_model=APIResponse, tags=["Analytics"])
def get_analytics():
    try:
        trades = get_all_trades(limit=500)
        today = datetime.now().strftime("%Y-%m-%d")
        today_pnl = get_daily_pnl(today)

        total_trades = len(trades)
        closed = [t for t in trades if t["status"] == "CLOSED"]
        winners = [t for t in closed if t["pnl"] > 0]
        losers = [t for t in closed if t["pnl"] < 0]

        total_pnl = sum(t["pnl"] for t in closed)
        total_gross_pnl = sum(t.get("gross_pnl", 0) for t in closed)
        total_charges = sum(t.get("total_charges", 0) for t in closed)
        win_rate = (len(winners) / len(closed) * 100) if closed else 0
        avg_win = (sum(t["pnl"] for t in winners) / len(winners)) if winners else 0
        avg_loss = (sum(t["pnl"] for t in losers) / len(losers)) if losers else 0

        data = {
            "total_trades": total_trades,
            "closed_trades": len(closed),
            "open_trades": total_trades - len(closed),
            "winners": len(winners),
            "losers": len(losers),
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "total_gross_pnl": round(total_gross_pnl, 2),
            "total_charges": round(total_charges, 2),
            "today_pnl": round(today_pnl, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0,
        }
        return APIResponse(success=True, message="Analytics computed", data=data)
    except Exception as e:
        logger.error(f"Analytics failed: {e}")
        return APIResponse(success=False, message=str(e))


@app.get("/analytics/daily", response_model=APIResponse, tags=["Analytics"])
def get_daily_trades(date: str = Query(None, description="Date YYYY-MM-DD")):
    try:
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        all_trades = get_all_trades(limit=500)
        trades = [t for t in all_trades if t["timestamp"].startswith(target_date)]
        pnl = get_daily_pnl(target_date)

        data = {
            "date": target_date,
            "trades": trades,
            "trade_count": len(trades),
            "daily_pnl": round(pnl, 2),
        }
        return APIResponse(success=True, message=f"Daily analytics for {target_date}", data=data)
    except Exception as e:
        logger.error(f"Daily analytics failed: {e}")
        return APIResponse(success=False, message=str(e))


# --- AutoTrade Config Endpoints ---
@app.post("/autotrade/enable", response_model=APIResponse, tags=["AutoTrade"])
def enable_autotrade():
    try:
        autotrade = get_autotrade_service()
        autotrade.enable()
        return APIResponse(success=True, message="AutoTrade enabled", data={"enabled": True})
    except Exception as e:
        logger.error(f"Enable autotrade failed: {e}")
        return APIResponse(success=False, message=str(e))


@app.post("/autotrade/disable", response_model=APIResponse, tags=["AutoTrade"])
def disable_autotrade():
    try:
        autotrade = get_autotrade_service()
        autotrade.disable()
        return APIResponse(success=True, message="AutoTrade disabled", data={"enabled": False})
    except Exception as e:
        logger.error(f"Disable autotrade failed: {e}")
        return APIResponse(success=False, message=str(e))


@app.get("/autotrade/status", response_model=APIResponse, tags=["AutoTrade"])
def get_autotrade_status():
    try:
        autotrade = get_autotrade_service()
        rate_limited = False
        cooldown_remaining = 0
        if autotrade._rate_limited_until and datetime.now() < autotrade._rate_limited_until:
            rate_limited = True
            cooldown_remaining = int((autotrade._rate_limited_until - datetime.now()).total_seconds())
        return APIResponse(
            success=True,
            message="AutoTrade status fetched",
            data={
                "enabled": autotrade.is_enabled,
                "rate_limited": rate_limited,
                "cooldown_remaining": cooldown_remaining
            }
        )
    except Exception as e:
        logger.error(f"AutoTrade status fetch failed: {e}")
        return APIResponse(success=False, message=str(e))


@app.get("/autotrade/settings", response_model=APIResponse, tags=["AutoTrade"])
def get_settings_endpoint():
    try:
        from config import get_settings
        settings = get_settings()
        return APIResponse(
            success=True,
            message="Settings fetched",
            data={
                "max_daily_loss": settings.max_daily_loss,
                "risk_percent": settings.risk_percent,
                "default_quantity": settings.default_quantity,
                "min_risk_reward": settings.min_risk_reward,
                "max_open_trades": settings.max_open_trades,
                "paper_trading": settings.paper_trading,
            }
        )
    except Exception as e:
        logger.error(f"Get settings failed: {e}")
        return APIResponse(success=False, message=str(e))


@app.post("/autotrade/settings", response_model=APIResponse, tags=["AutoTrade"])
def update_settings_endpoint(payload: dict):
    try:
        from config import get_settings
        settings = get_settings()
        if "max_daily_loss" in payload:
            settings.max_daily_loss = float(payload["max_daily_loss"])
        if "risk_percent" in payload:
            settings.risk_percent = float(payload["risk_percent"])
        if "default_quantity" in payload:
            settings.default_quantity = int(payload["default_quantity"])
        if "min_risk_reward" in payload:
            settings.min_risk_reward = float(payload["min_risk_reward"])
        if "max_open_trades" in payload:
            settings.max_open_trades = int(payload["max_open_trades"])
        if "paper_trading" in payload:
            settings.paper_trading = bool(payload["paper_trading"])
            
        logger.info(f"Settings updated: {settings.__dict__}")
        return APIResponse(
            success=True,
            message="Settings updated successfully",
            data={
                "max_daily_loss": settings.max_daily_loss,
                "risk_percent": settings.risk_percent,
                "default_quantity": settings.default_quantity,
                "min_risk_reward": settings.min_risk_reward,
                "max_open_trades": settings.max_open_trades,
                "paper_trading": settings.paper_trading,
            }
        )
    except Exception as e:
        logger.error(f"Update settings failed: {e}")
        return APIResponse(success=False, message=str(e))


@app.get("/autotrade/last-decision", response_model=APIResponse, tags=["AutoTrade"])
def get_last_decision():
    try:
        autotrade = get_autotrade_service()
        return APIResponse(
            success=True,
            message="Last decision fetched",
            data=autotrade.last_analysis
        )
    except Exception as e:
        logger.error(f"Get last decision failed: {e}")
        return APIResponse(success=False, message=str(e))



# --- Chat Endpoint ---
@app.post("/chat", response_model=APIResponse, tags=["Chat"])
def process_chat(request: ChatRequest):
    msg = request.message.strip().lower()
    kotak = get_kotak_service()
    autotrade = get_autotrade_service()
    trade_service = TradeService(kotak)

    # 1. TOTP Login intent
    totp_match = re.search(r'\b(\d{6})\b', msg)
    if totp_match:
        totp_code = totp_match.group(1)
        try:
            kotak.login(totp_code)
            return APIResponse(
                success=True,
                message="Successfully authenticated with Kotak Neo!",
                data={"reply": "**Login Successful!**\n\nI have verified your TOTP code and established a live session with Kotak Neo. You can now fetch live prices, analyze indices, and place options trades."}
            )
        except Exception as e:
            return APIResponse(
                success=True,
                message="Authentication failed",
                data={"reply": f"**Login Failed**\n\nFailed to authenticate with Kotak Neo: `{str(e)}`. Please generate a fresh 6-digit TOTP code and try again."}
            )

    # Check connection status
    is_auth = kotak.is_authenticated

    # 2. Help Intent
    if "help" in msg or "command" in msg or msg == "?":
        reply = (
            "**Hi! I'm your AI Options Trading Assistant.**\n\n"
            "Here is what you can ask me to do:\n\n"
            "* **Market Status**: `nifty price`, `banknifty price`, `market overview`\n"
            "* **AI Scan**: `analyze nifty`, `analyze banknifty` (runs indicators, volume & OI scan)\n"
            "* **Portfolio Details**: `show positions`, `show holdings`, `available margin`\n"
            "* **Autotrading**: `enable autotrade`, `disable autotrade`, `autotrade status`\n"
            "* **Trade Journal**: `show history`, `show trade logs`\n"
            "* **Manual Order**: `buy NIFTY CE strike 24200 expiry 2026-07-02 quantity 50`\n"
            "* **Login**: Just paste a fresh **6-digit TOTP** code directly here!\n\n"
            "How can I help you today?"
        )
        return APIResponse(success=True, message="Help reply", data={"reply": reply})

    # 3. Autotrade Toggle Intents
    if "enable autotrade" in msg or "start autotrade" in msg:
        autotrade.enable()
        return APIResponse(
            success=True,
            message="AutoTrade enabled",
            data={"reply": "**Auto-Trading Mode ENABLED!**\n\nI am now scanning NIFTY and BANKNIFTY in the background every 120 seconds during market hours. I will automatically execute high-confidence signals that pass the risk engine."}
        )
    if "disable autotrade" in msg or "stop autotrade" in msg:
        autotrade.disable()
        return APIResponse(
            success=True,
            message="AutoTrade disabled",
            data={"reply": "**Auto-Trading Mode DISABLED.**\n\nBackground scanning paused. You can still trade manually or trigger AI scans on-demand."}
        )
    if "autotrade" in msg:
        status_str = "**ENABLED**" if autotrade.is_enabled else "**DISABLED**"
        return APIResponse(
            success=True,
            message="AutoTrade status",
            data={"reply": f"**Auto-Trading Status**\n\nCurrently: {status_str}\n\nTo change, say `enable autotrade` or `disable autotrade`."}
        )

    # Block other operations if not authenticated
    if not is_auth:
        return APIResponse(
            success=True,
            message="Authentication required",
            data={"reply": "**Authentication Required**\n\nYou are not logged into Kotak Neo. Please send your 6-digit Google Authenticator **TOTP code** (e.g., `123456`) to log in and get started."}
        )

    # 4. Market Overview Intents
    if "market" in msg or "overview" in msg or "indices" in msg:
        try:
            overview = kotak.get_market_overview()
            n = overview["nifty"]
            b = overview["banknifty"]
            v = overview["india_vix"]
            reply = (
                "**Live Market Overview**\n\n"
                f"**NIFTY 50**:\n"
                f"* LTP: `₹{n['ltp']:.2f}`\n"
                f"* High: `₹{n['high']:.2f}` | Low: `₹{n['low']:.2f}`\n"
                f"* Prev Close: `₹{n['close']:.2f}`\n\n"
                f"**BANKNIFTY**:\n"
                f"* LTP: `₹{b['ltp']:.2f}`\n"
                f"* High: `₹{b['high']:.2f}` | Low: `₹{b['low']:.2f}`\n"
                f"* Prev Close: `₹{b['close']:.2f}`\n\n"
                f"**India VIX**: `{v.get('vix', 'N/A')}`\n\n"
                f"_Updated: {overview['timestamp'].split('T')[1][:8]} (IST)_"
            )
            return APIResponse(success=True, message="Market overview", data={"reply": reply})
        except Exception as e:
            return APIResponse(success=True, message="Error", data={"reply": f"Error fetching market overview: `{str(e)}`"})

    # 5. Index Price Intents
    if "nifty" in msg and ("price" in msg or "ltp" in msg or "status" in msg or msg == "nifty"):
        try:
            p = kotak.get_nifty_price()
            return APIResponse(
                success=True,
                message="Nifty price",
                data={"reply": f"**NIFTY 50**: `₹{p.ltp:.2f}` (High: `₹{p.high:.2f}` / Low: `₹{p.low:.2f}`)"}
            )
        except Exception as e:
            return APIResponse(success=True, message="Error", data={"reply": f"Error: `{str(e)}`"})
            
    if "banknifty" in msg and ("price" in msg or "ltp" in msg or "status" in msg or msg == "banknifty"):
        try:
            p = kotak.get_banknifty_price()
            return APIResponse(
                success=True,
                message="BankNifty price",
                data={"reply": f"**BANKNIFTY**: `₹{p.ltp:.2f}` (High: `₹{p.high:.2f}` / Low: `₹{p.low:.2f}`)"}
            )
        except Exception as e:
            return APIResponse(success=True, message="Error", data={"reply": f"Error: `{str(e)}`"})

    # 6. AI Scan Intent
    if "analyze" in msg or "scan" in msg:
        symbol = "BANKNIFTY" if "bank" in msg else "NIFTY"
        try:
            nifty_ohlc = kotak.get_nifty_ohlc()
            banknifty_ohlc = kotak.get_banknifty_ohlc()
            spot_data = nifty_ohlc if symbol == "NIFTY" else banknifty_ohlc
            
            chain = kotak.get_option_chain(symbol)
            vix = kotak.get_india_vix()
            
            ai = LLMService()
            strategy = StrategyService()
            res = ai.analyze_with_llm(nifty_ohlc, banknifty_ohlc, chain, vix)
            
            opt_type = "CE" if res.signal == SignalType.BUY_CALL else "PE"
            atm = kotak.get_atm_option_details(symbol, opt_type, spot_data.ltp)
            rec = strategy.evaluate(res, symbol, atm)
            
            reply = (
                f"**AI Option Chain Analyzer — {symbol}**\n\n"
                f"* **Trend**: `{res.trend.value}`\n"
                f"* **Signal**: **{res.signal.value}**\n"
                f"* **Confidence**: `{res.confidence}%`\n"
                f"* **Scorer Reason**: `{res.reason}`\n\n"
            )
            
            if res.signal in [SignalType.BUY_CALL, SignalType.BUY_PUT] and atm.get("trading_symbol"):
                reply += (
                    f"**Strategy Recommendation**:\n"
                    f"* Instrument: `{atm['trading_symbol']}`\n"
                    f"* Entry Premium: `₹{rec.entry_price:.2f}`\n"
                    f"* Target (40%): `₹{rec.target:.2f}`\n"
                    f"* Stoploss (20%): `₹{rec.stoploss:.2f}`\n"
                    f"* Default Qty: `{rec.quantity}` units\n"
                )
            else:
                reply += "System: **No active trade recommended** due to neutral trend or insufficient scan confidence."
                
            return APIResponse(success=True, message="Analysis complete", data={"reply": reply})
        except Exception as e:
            return APIResponse(success=True, message="Error", data={"reply": f"Analysis failed: `{str(e)}`"})

    # 7. Portfolio / Margin Intents
    if "positions" in msg:
        try:
            pos = trade_service.get_positions()
            recs = pos if isinstance(pos, list) else pos.get("data", [])
            if not recs or not isinstance(recs, list):
                return APIResponse(success=True, message="No positions found", data={"reply": "**Positions**: No active positions found in your account."})
            
            reply = "**Active Positions**\n\n| Symbol | Qty | Avg Price | LTP | P&L |\n| :--- | :--- | :--- | :--- | :--- |\n"
            for p in recs:
                pnl = p.get("pnl", 0)
                reply += f"| {p.get('tradingSymbol', p.get('symbol', ''))} | {p.get('qty', p.get('quantity', 0))} | ₹{p.get('buyAvg', p.get('avgPrice', 0))} | ₹{p.get('lastPrice', p.get('ltp', 0))} | ₹{pnl} |\n"
            return APIResponse(success=True, message="Positions fetched", data={"reply": reply})
        except Exception as e:
            return APIResponse(success=True, message="Error", data={"reply": f"Failed to fetch positions: `{str(e)}`"})

    if "holdings" in msg:
        try:
            hld = kotak.get_holdings()
            recs = hld if isinstance(hld, list) else hld.get("data", [])
            if not recs or not isinstance(recs, list):
                return APIResponse(success=True, message="No holdings found", data={"reply": "**Holdings**: No stock holdings found."})
                
            reply = "**Account Holdings**\n\n| Symbol | Qty | Avg Price | LTP | Current Value |\n| :--- | :--- | :--- | :--- | :--- |\n"
            for h in recs:
                reply += f"| {h.get('tradingSymbol', h.get('symbol', ''))} | {h.get('qty', h.get('quantity', 0))} | ₹{h.get('buyAvg', h.get('avgCost', 0))} | ₹{h.get('lastPrice', h.get('ltp', 0))} | ₹{h.get('currentValue', 0)} |\n"
            return APIResponse(success=True, message="Holdings fetched", data={"reply": reply})
        except Exception as e:
            return APIResponse(success=True, message="Error", data={"reply": f"Failed to fetch holdings: `{str(e)}`"})

    if "portfolio" in msg or "margin" in msg or "limits" in msg or "balance" in msg:
        try:
            lim = kotak.get_limits()
            net = lim.get("Net", lim.get("data", {}).get("Net", "0"))
            return APIResponse(
                success=True,
                message="Limits fetched",
                data={"reply": f"Available Margin / Net Limits: `₹{net}`\n\nTo view asset lists, ask me to `show positions` or `show holdings`."}
            )
        except Exception as e:
            return APIResponse(success=True, message="Error", data={"reply": f"Failed to fetch limits: `{str(e)}`"})

    # 8. History Intent
    if "history" in msg or "trades" in msg or "journal" in msg or "pnl" in msg:
        try:
            hist = trade_service.get_history(limit=5)
            if not hist:
                return APIResponse(success=True, data={"reply": "**Trade Journal**: No logged trades found in the SQLite database."})
            
            reply = "**Recent Trade Journal Logs**\n\n| Date | Symbol | Option | Strike | Qty | P&L | Status |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            for t in hist:
                date_str = t["timestamp"].split("T")[0]
                pnl = t.get("pnl", 0)
                reply += f"| {date_str} | {t['symbol']} | {t['option_type']} | {t['strike']} | {t['quantity']} | ₹{pnl:.2f} | `{t['status']}` |\n"
            return APIResponse(success=True, message="History fetched", data={"reply": reply})
        except Exception as e:
            return APIResponse(success=True, message="Error", data={"reply": f"Failed to fetch history: `{str(e)}`"})

    # 9. Order parsing Intent
    if msg.startswith("buy ") or msg.startswith("trade "):
        try:
            symbol_match = re.search(r'\b(nifty|banknifty)\b', msg)
            opt_match = re.search(r'\b(ce|pe|call|put)\b', msg)
            strike_match = re.search(r'(?:strike\s+)?(\d{5})', msg)
            expiry_match = re.search(r'(?:expiry\s+)?(\d{4}-\d{2}-\d{2})', msg)
            qty_match = re.search(r'(?:qty|quantity|lot|lots\s+)?(\d+)\b', msg)
            sl_match = re.search(r'(?:sl|stoploss|stop\s+)?(\d+)\b', msg)
            target_match = re.search(r'(?:target|limit\s+)?(\d+)\b', msg)
            
            if not (symbol_match and opt_match and strike_match and expiry_match):
                raise ValueError("Missing parameters. Format: `buy [nifty|banknifty] [CE|PE] strike [strike] expiry [YYYY-MM-DD] [qty 50] [sl price] [target price]`")
                
            symbol = symbol_match.group(1).upper()
            opt_type = "CALL" if opt_match.group(1) in ["ce", "call"] else "PUT"
            strike = float(strike_match.group(1))
            expiry = expiry_match.group(1)
            quantity = int(qty_match.group(1)) if qty_match else None
            stoploss = float(sl_match.group(1)) if sl_match else None
            target = float(target_match.group(1)) if target_match else None
            
            buy_req = BuyRequest(
                symbol=symbol,
                strike=strike,
                expiry=expiry,
                option_type=opt_type,
                quantity=quantity,
                stoploss=stoploss,
                target=target,
                reason="Manual buy order via Chat Assistant"
            )
            
            res = trade_service.buy(buy_req)
            reply = (
                f"**Order Dispatched Successfully!**\n\n"
                f"* Asset: `{symbol} {strike} {opt_type}`\n"
                f"* Expiry: `{expiry}`\n"
                f"* Order ID: `{res.get('order_id')}`\n"
                f"* Trading Symbol: `{res.get('trading_symbol')}`\n"
                f"* Quantity: `{quantity or 'Default'}`\n"
                f"* Stoploss: `{stoploss or 'N/A'}` | Target: `{target or 'N/A'}`\n\n"
                f"_Trade logged under internal ID `{res.get('trade_id')}`. Check the Positions panel to monitor live PnL._"
            )
            return APIResponse(success=True, message="Order placed", data={"reply": reply})
        except Exception as e:
            return APIResponse(
                success=True, 
                message="Parsing failed", 
                data={"reply": f"**Invalid Order Format or Execution Error**\n\nError: `{str(e)}`\n\nTry prompting like this:\n`buy NIFTY CE strike 24200 expiry 2026-07-02 qty 50 sl 150 target 250`"}
            )

    # 10. Fallback message
    reply = (
        "**I'm not sure how to handle that request.**\n\n"
        "Here are some ideas on what you can type:\n"
        "- `market overview` (shows Nifty/BankNifty spot rates)\n"
        "- `analyze nifty` (runs trend and OI analyzer)\n"
        "- `show positions` (lists active trades)\n"
        "- `enable autotrade` (toggles background scanner loops)\n"
        "- Or paste a fresh **6-digit TOTP** to reconnect your Kotak account.\n\n"
        "Type `help` to see the complete list."
    )
    return APIResponse(success=True, message="Fallback reply", data={"reply": reply})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False, ws="none")
