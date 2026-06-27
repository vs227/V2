from fastapi import APIRouter
from schemas import APIResponse, ChatRequest, BuyRequest, LoginRequest
from services.kotak_service import get_kotak_service
from services.market_service import MarketService
from services.llm_ai_service import LLMService
from services.strategy_service import StrategyService
from services.risk_service import RiskService
from services.trade_service import TradeService
from services.autotrade_service import get_autotrade_service
import re

router = APIRouter(prefix="/chat", tags=["Chat"])

kotak = get_kotak_service()
market = MarketService(kotak)
ai = LLMService()
strategy = StrategyService()
risk = RiskService()
trade_service = TradeService(kotak)
autotrade = get_autotrade_service()

@router.post("", response_model=APIResponse)
def process_chat(request: ChatRequest):
    msg = request.message.strip().lower()
    
    # 1. TOTP Login intent
    totp_match = re.search(r'\b(\d{6})\b', msg)
    if totp_match:
        totp_code = totp_match.group(1)
        try:
            res = kotak.login(totp_code)
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

    # Check connection for other intents
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
        autotrade.start()
        return APIResponse(
            success=True,
            message="AutoTrade enabled",
            data={"reply": "**Auto-Trading Mode ENABLED!**\n\nI am now scanning NIFTY and BANKNIFTY in the background every 60 seconds during market hours. I will automatically execute high-confidence signals that pass the risk engine."}
        )
    if "disable autotrade" in msg or "stop autotrade" in msg:
        autotrade.stop()
        return APIResponse(
            success=True,
            message="AutoTrade disabled",
            data={"reply": "**Auto-Trading Mode DISABLED.**\n\nBackground scanning paused. You can still trade manually or trigger AI scans on-demand."}
        )
    if "autotrade" in msg:
        status_str = "**ENABLED**" if autotrade.is_enabled() else "**DISABLED**"
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
            overview = market.get_market_overview()
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
            p = market.get_nifty_price()
            return APIResponse(
                success=True,
                message="Nifty price",
                data={"reply": f"**NIFTY 50**: `₹{p.ltp:.2f}` (High: `₹{p.high:.2f}` / Low: `₹{p.low:.2f}`)"}
            )
        except Exception as e:
            return APIResponse(success=True, message="Error", data={"reply": f"Error: `{str(e)}`"})
            
    if "banknifty" in msg and ("price" in msg or "ltp" in msg or "status" in msg or msg == "banknifty"):
        try:
            p = market.get_banknifty_price()
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
            # Fetch spot
            nifty_ohlc = market.get_nifty_ohlc()
            banknifty_ohlc = market.get_banknifty_ohlc()
            spot_data = nifty_ohlc if symbol == "NIFTY" else banknifty_ohlc
            
            # Fetch chain
            chain = market.get_option_chain(symbol)
            vix = market.get_india_vix()
            
            # Analyze
            res = ai.analyze_with_llm(nifty_ohlc, banknifty_ohlc, chain, vix)
            
            # Rec
            opt_type = "CE" if res.signal == "BUY_CALL" else "PE"
            atm = market.get_atm_option_details(symbol, opt_type, spot_data.ltp)
            rec = strategy.evaluate(res, symbol, atm)
            
            reply = (
                f"**AI Option Chain Analyzer — {symbol}**\n\n"
                f"* **Trend**: `{res.trend.value}`\n"
                f"* **Signal**: **{res.signal.value}**\n"
                f"* **Confidence**: `{res.confidence}%`\n"
                f"* **Scorer Reason**: `{res.reason}`\n\n"
            )
            
            if res.signal in ["BUY_CALL", "BUY_PUT"] and atm.get("trading_symbol"):
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
            # If list or dict
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
    # e.g., buy nifty call strike 24200 expiry 2026-07-02 qty 50 sl 180 target 250
    if msg.startswith("buy ") or msg.startswith("trade "):
        try:
            # Parse parameters via regex
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
            
            # Place buy
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
