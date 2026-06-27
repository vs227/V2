from datetime import datetime, timedelta
import pytz
import random
import json
import re
import gc
from groq import Groq
from apscheduler.schedulers.background import BackgroundScheduler
from config import get_settings
from logger import setup_logger
from schemas import (
    BuyRequest, ExitRequest, SellRequest,
    AnalysisResult, StrategyRecommendation, RiskDecision,
    TrendDirection, SignalType, TradeStatus, OptionType
)
from database import (
    insert_trade, update_trade, get_trade,
    get_open_trades, get_all_trades, get_daily_pnl
)
from services.kotak_service import get_kotak_service

logger = setup_logger("autotrade")


class FnOCharges:
    """Calculates realistic NSE F&O charges for options trading (2025-2026 rates)"""
    BROKERAGE_PER_ORDER = 20.0
    STT_RATE = 0.000625  # 0.0625% on sell side
    NSE_TXN_CHARGES = 0.00005  # 0.005% both sides
    GST_RATE = 0.18  # 18% on brokerage + txn charges
    SEBI_FEES = 0.0000001  # Rs. 10 per crore
    STAMP_DUTY_RATE = 0.000015  # Rs. 15 per lakh on buy side

    @classmethod
    def calculate_charges(cls, entry_price: float, exit_price: float, quantity: int) -> dict:
        buy_turnover = entry_price * quantity
        sell_turnover = exit_price * quantity
        total_turnover = buy_turnover + sell_turnover

        brokerage = cls.BROKERAGE_PER_ORDER * 2
        stt = sell_turnover * cls.STT_RATE
        txn_charges = total_turnover * cls.NSE_TXN_CHARGES
        gst = (brokerage + txn_charges) * cls.GST_RATE
        sebi_fees = total_turnover * cls.SEBI_FEES
        stamp_duty = buy_turnover * cls.STAMP_DUTY_RATE

        total_charges = brokerage + stt + txn_charges + gst + sebi_fees + stamp_duty
        return {
            "brokerage": round(brokerage, 2),
            "stt": round(stt, 2),
            "transaction_charges": round(txn_charges, 2),
            "gst": round(gst, 2),
            "sebi_fees": round(sebi_fees, 4),
            "stamp_duty": round(stamp_duty, 4),
            "total_charges": round(total_charges, 2)
        }

    @classmethod
    def calculate_net_pnl(cls, entry_price: float, exit_price: float, quantity: int) -> dict:
        gross_pnl = (exit_price - entry_price) * quantity
        charges = cls.calculate_charges(entry_price, exit_price, quantity)
        net_pnl = gross_pnl - charges["total_charges"]
        return {
            "gross_pnl": round(gross_pnl, 2),
            "charges": charges,
            "net_pnl": round(net_pnl, 2)
        }


class StrategyService:
    """Evaluates option type, strike, stoploss, and target recommendations"""
    def evaluate(self, analysis: AnalysisResult, symbol: str = "NIFTY", atm_details: dict = None) -> StrategyRecommendation:
        settings = get_settings()
        if analysis.signal == SignalType.NO_TRADE or analysis.confidence < 50:
            return StrategyRecommendation(
                action=SignalType.NO_TRADE, symbol=symbol, strike=0,
                option_type=OptionType.CALL, entry_price=0, stoploss=0, target=0,
                quantity=settings.default_quantity, reason="No trade setup", confidence=analysis.confidence
            )

        entry = 200.0
        strike = 0.0
        option_type = OptionType.CALL if analysis.trend == TrendDirection.BULLISH else OptionType.PUT

        if atm_details:
            entry = atm_details.get("ltp", 200.0) or 200.0
            strike = atm_details.get("strike", 0.0)
            option_type = OptionType.CALL if atm_details.get("option_type") == "CE" else OptionType.PUT

        stoploss = entry * 0.80
        target = entry * 1.40
        action = SignalType.BUY_CALL if analysis.trend == TrendDirection.BULLISH else SignalType.BUY_PUT
        reason = f"{analysis.trend.value} setup: {analysis.reason}"
        if atm_details and atm_details.get("trading_symbol"):
            reason += f" | ATM Option: {atm_details['trading_symbol']}"

        return StrategyRecommendation(
            action=action, symbol=symbol, strike=strike, option_type=option_type,
            entry_price=round(entry, 2), stoploss=round(stoploss, 2), target=round(target, 2),
            quantity=settings.default_quantity, reason=reason, confidence=analysis.confidence
        )


class RiskService:
    """Evaluates capital risk limits, daily loss thresholds, and risk reward metrics"""
    def evaluate(self, rec: StrategyRecommendation) -> RiskDecision:
        settings = get_settings()
        
        open_trades = get_open_trades()
        if len(open_trades) >= settings.max_open_trades:
            return RiskDecision(approved=False, reason=f"Max open trades reached ({settings.max_open_trades})")

        today = datetime.now().strftime("%Y-%m-%d")
        daily_pnl = get_daily_pnl(today)
        if daily_pnl <= -settings.max_daily_loss:
            return RiskDecision(approved=False, reason=f"Daily loss limit hit: ₹{abs(daily_pnl):.2f}/₹{settings.max_daily_loss}")

        if rec.entry_price <= 0 or rec.stoploss <= 0 or rec.target <= 0:
            return RiskDecision(approved=False, reason="Invalid entry/SL/target pricing")

        risk_per_unit = abs(rec.entry_price - rec.stoploss)
        reward_per_unit = abs(rec.target - rec.entry_price)
        if risk_per_unit == 0:
            return RiskDecision(approved=False, reason="Risk per unit is zero")

        risk_reward = reward_per_unit / risk_per_unit
        if risk_reward < settings.min_risk_reward:
            return RiskDecision(approved=False, reason=f"Risk:Reward {risk_reward:.2f} below {settings.min_risk_reward}", risk_reward_ratio=round(risk_reward, 2))

        risk_amount = risk_per_unit * rec.quantity
        max_risk = (settings.risk_percent / 100) * settings.max_daily_loss * 10
        if risk_amount > max_risk:
            return RiskDecision(approved=False, reason=f"Risk amount ₹{risk_amount:.2f} exceeds limit ₹{max_risk:.2f}", risk_amount=risk_amount)

        return RiskDecision(approved=True, reason="All checks passed", risk_amount=round(risk_amount, 2), risk_reward_ratio=round(risk_reward, 2))


class LLMService:
    """Performs LLM-based option chain scans using Groq API"""
    def __init__(self):
        settings = get_settings()
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is required.")
        self.client = Groq(api_key=settings.groq_api_key)

    def analyze_with_llm(self, nifty_data: MarketData, banknifty_data: MarketData, option_chain: dict, vix: dict) -> AnalysisResult:
        spot_price = nifty_data.ltp
        contracts = option_chain.get("data", option_chain.get("scrip", []))
        if contracts and "BANKNIFTY" in contracts[0].get("tradingSymbol", contracts[0].get("pTrdSym", "")):
            spot_price = banknifty_data.ltp

        pruned_chain = self._prune_option_chain(option_chain)
        prompt = f"""
NIFTY 50: LTP={nifty_data.ltp}, Open={nifty_data.open}, High={nifty_data.high}, Low={nifty_data.low}, PrevClose={nifty_data.close}
BANKNIFTY: LTP={banknifty_data.ltp}, Open={banknifty_data.open}, High={banknifty_data.high}, Low={banknifty_data.low}, PrevClose={banknifty_data.close}
VIX: {vix}
Option Chain Summary (Nearest strikes):
{pruned_chain}

Analyze this data for a short-term scalping opportunity.
"""
        completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": 'Respond ONLY in JSON:\n{"trend": "BULLISH"|"BEARISH"|"SIDEWAYS", "signal": "BUY_CALL"|"BUY_PUT"|"NO_TRADE", "confidence": 0-100, "reasoning": "brief explain"}'},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.1,
            max_tokens=300
        )
        response_text = completion.choices[0].message.content.strip()
        match = re.search(r'\{[^{}]*\}', response_text)
        if not match:
            raise ValueError("Invalid LLM response format")
        
        res_json = json.loads(match.group())
        return AnalysisResult(
            trend=TrendDirection(res_json.get("trend", "SIDEWAYS")),
            confidence=float(res_json.get("confidence", 0)),
            signal=SignalType(res_json.get("signal", "NO_TRADE")),
            reason=res_json.get("reasoning", "LLM scan")
        )

    def _prune_option_chain(self, option_chain: dict) -> str:
        data_list = option_chain.get("data", [])
        if not data_list:
            return "No data available."
        lines = []
        for item in data_list[:6]:
            ce = item.get("CE")
            pe = item.get("PE")
            ce_str = f"CE LTP: {ce['ltp']} (Vol: {ce['volume']}, OI: {ce['oi']})" if ce else "CE: N/A"
            pe_str = f"PE LTP: {pe['ltp']} (Vol: {pe['volume']}, OI: {pe['oi']})" if pe else "PE: N/A"
            lines.append(f"Strike {item.get('strike')}: {ce_str} | {pe_str}")
        return "\n".join(lines)


class TradeService:
    """Handles order placement, exits, modifications and journal logging"""
    def __init__(self, kotak) -> None:
        self.kotak = kotak

    def buy(self, request: BuyRequest) -> dict:
        settings = get_settings()
        quantity = request.quantity or settings.default_quantity
        trading_symbol = f"{request.symbol}{request.expiry.replace('-', '')}{int(request.strike)}{'CE' if request.option_type.upper() in ('CALL', 'CE') else 'PE'}"

        entry_price = 120.0
        try:
            ot_key = "CE" if request.option_type.upper() in ("CALL", "CE") else "PE"
            search_res = self.kotak.search_scrip(
                exchange_segment="nse_fo", symbol=request.symbol, expiry=request.expiry,
                option_type=ot_key, strike_price=str(int(request.strike))
            )
            contracts = search_res.get("data", []) if isinstance(search_res, dict) else search_res
            if contracts and isinstance(contracts, list):
                token = contracts[0].get("pInstToken", contracts[0].get("instrumentToken", ""))
                if token:
                    quote = self.kotak.get_quotes([{"instrument_token": str(token), "exchange_segment": "nse_fo"}])
                    entry_price = float(quote.get("data", [{}])[0].get("ltp", 120.0))
        except Exception as e:
            logger.warning(f"Could not resolve entry price: {e}")

        entry_price = max(0.1, entry_price)
        stoploss = request.stoploss or round(entry_price * 0.80, 2)
        target = request.target or round(entry_price * 1.40, 2)

        order_resp = self.kotak.place_order(
            exchange_segment="nse_fo", product="MIS", price="0", order_type="MKT",
            quantity=str(quantity), validity="DAY", trading_symbol=trading_symbol, transaction_type="B"
        )
        order_id = str(order_resp.get("nOrdNo", order_resp.get("orderId", "")))

        trade_id = insert_trade({
            "timestamp": datetime.now().isoformat(),
            "symbol": request.symbol, "strike": request.strike, "expiry": request.expiry,
            "option_type": request.option_type, "entry_price": entry_price, "exit_price": None,
            "quantity": quantity, "stoploss": stoploss, "target": target, "pnl": 0.0,
            "strategy": "MANUAL" if "Manual" in (request.reason or "") else "AI_SYSTEM",
            "reason": request.reason or "Manual buy order", "status": TradeStatus.OPEN, "order_id": order_id
        })

        return {
            "trade_id": trade_id, "order_id": order_id, "trading_symbol": trading_symbol,
            "entry_price": entry_price, "stoploss": stoploss, "target": target, "order_response": order_resp
        }

    def exit_trade(self, request: ExitRequest) -> dict:
        trade = get_trade(request.trade_id)
        if not trade or trade["status"] != TradeStatus.OPEN:
            raise ValueError("Trade not found or not open")

        trading_symbol = f"{trade['symbol']}{trade['expiry'].replace('-', '')}{int(trade['strike'])}{'CE' if trade['option_type'] == 'CALL' else 'PE'}"

        exit_price = 150.0
        try:
            ot_key = "CE" if trade["option_type"] == "CALL" else "PE"
            search_res = self.kotak.search_scrip(
                exchange_segment="nse_fo", symbol=trade["symbol"], expiry=trade["expiry"],
                option_type=ot_key, strike_price=str(int(trade["strike"]))
            )
            contracts = search_res.get("data", []) if isinstance(search_res, dict) else search_res
            if contracts and isinstance(contracts, list):
                token = contracts[0].get("pInstToken", contracts[0].get("instrumentToken", ""))
                if token:
                    quote = self.kotak.get_quotes([{"instrument_token": str(token), "exchange_segment": "nse_fo"}])
                    exit_price = float(quote.get("data", [{}])[0].get("ltp", 150.0))
        except Exception as e:
            logger.warning(f"Could not resolve exit price: {e}")

        exit_price = max(0.1, exit_price)
        order_resp = self.kotak.place_order(
            exchange_segment="nse_fo", product="MIS", price="0", order_type="MKT",
            quantity=str(trade["quantity"]), validity="DAY", trading_symbol=trading_symbol, transaction_type="S"
        )

        pnl_res = FnOCharges.calculate_net_pnl(trade["entry_price"], exit_price, trade["quantity"])
        charges = pnl_res["charges"]

        update_trade(request.trade_id, {
            "status": TradeStatus.CLOSED, "exit_price": exit_price, "pnl": pnl_res["net_pnl"],
            "gross_pnl": pnl_res["gross_pnl"], "total_charges": charges["total_charges"],
            "brokerage": charges["brokerage"], "stt": charges["stt"], "transaction_charges": charges["transaction_charges"],
            "gst": charges["gst"], "sebi_fees": charges["sebi_fees"], "stamp_duty": charges["stamp_duty"],
            "reason": request.reason or trade.get("reason", "")
        })

        return {
            "trade_id": request.trade_id, "exit_price": exit_price, "pnl": pnl_res["net_pnl"],
            "gross_pnl": pnl_res["gross_pnl"], "charges": charges, "order_response": order_resp
        }

    def cancel_order(self, order_id: str) -> dict:
        return {"order_id": order_id, "response": self.kotak.cancel_order(order_id)}

    def get_positions(self) -> dict:
        return self.kotak.get_positions()

    def get_history(self, limit: int = 100) -> list[dict]:
        return get_all_trades(limit)

    def get_open(self) -> list[dict]:
        return get_open_trades()


class AutoTradeService:
    """Manages automated trading execution loops and scanning"""
    def __init__(self) -> None:
        self.kotak = get_kotak_service()
        self.ai = LLMService()
        self.strategy = StrategyService()
        self.risk = RiskService()
        self.trade = TradeService(self.kotak)

        self.scheduler = BackgroundScheduler()
        self.enabled = False
        self.target_timezone = pytz.timezone("Asia/Kolkata")
        self._rate_limited_until = None
        self.last_analysis = None

        self.scheduler.add_job(self.run_scan, "interval", seconds=120, id="autotrade_scan_job")
        self.scheduler.add_job(self.run_fast_monitor, "interval", seconds=2, id="autotrade_monitor_job")
        self.scheduler.add_job(self.run_gc, "interval", seconds=60, id="autotrade_gc_job")

        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("AutoTrade Scheduler started.")

    def run_gc(self) -> None:
        import gc
        collected = gc.collect()
        logger.info(f"AutoTrade: Periodic GC freed {collected} objects.")

    def run_fast_monitor(self) -> None:
        if not self.enabled or not self.kotak.is_authenticated:
            return
        self._check_and_manage_trades()

    def enable(self) -> None:
        self.enabled = True
        logger.info("AutoTrade ENABLED.")

    def disable(self) -> None:
        self.enabled = False
        logger.info("AutoTrade DISABLED.")

    @property
    def is_enabled(self) -> bool:
        return self.enabled

    def is_market_hours(self) -> bool:
        now = datetime.now(self.target_timezone)
        if now.weekday() >= 5:
            return False
        start = now.replace(hour=9, minute=15, second=0, microsecond=0)
        end = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return start <= now <= end

    def _check_and_manage_trades(self) -> None:
        open_trades = self.trade.get_open()
        if not open_trades:
            return

        for ot in open_trades:
            trade_id = ot["id"]
            try:
                ot_key = "CE" if ot["option_type"].upper() in ("CALL", "CE") else "PE"
                search_res = self.kotak.search_scrip(
                    exchange_segment="nse_fo", symbol=ot["symbol"], expiry=ot.get("expiry", ""),
                    option_type=ot_key, strike_price=str(int(ot["strike"]))
                )
                contracts = search_res.get("data", [])
                if not contracts:
                    continue

                token = contracts[0].get("pInstToken", contracts[0].get("instrumentToken", ""))
                if not token:
                    continue

                quote = self.kotak.get_quotes([{"instrument_token": str(token), "exchange_segment": "nse_fo"}])
                ltp = float(quote.get("data", [{}])[0].get("ltp", 0.0))
                if ltp <= 0:
                    continue

                if ltp >= ot["target"]:
                    logger.info(f"Trade #{trade_id} target hit. Exiting.")
                    self.trade.exit_trade(ExitRequest(trade_id=trade_id, reason="Auto-Exit: Target hit"))
                elif ltp <= ot["stoploss"]:
                    logger.info(f"Trade #{trade_id} stoploss hit. Exiting.")
                    self.trade.exit_trade(ExitRequest(trade_id=trade_id, reason="Auto-Exit: Stoploss hit"))
            except Exception as e:
                logger.error(f"Error checking trade #{trade_id}: {e}")

    def run_scan(self) -> None:
        if not self.enabled or not self.kotak.is_authenticated:
            return

        if self._rate_limited_until and datetime.now() < self._rate_limited_until:
            return

        # Skip scanning outside Indian market hours to preserve API limits
        if not self.is_market_hours():
            logger.info("AutoTrade scan skipped: Market is closed.")
            return

        logger.info("Starting automated market scan...")
        for symbol in ["NIFTY", "BANKNIFTY"]:
            try:
                nifty_ohlc = self.kotak.get_nifty_ohlc()
                banknifty_ohlc = self.kotak.get_banknifty_ohlc()
                spot_data = nifty_ohlc if symbol == "NIFTY" else banknifty_ohlc
                
                chain = self.kotak.get_option_chain(symbol)
                vix = self.kotak.get_india_vix()

                analysis = self.ai.analyze_with_llm(nifty_ohlc, banknifty_ohlc, chain, vix)
                self.last_analysis = {
                    "symbol": symbol, "trend": analysis.trend.value, "signal": analysis.signal.value,
                    "confidence": analysis.confidence, "reason": analysis.reason, "timestamp": datetime.now().isoformat()
                }

                if analysis.signal in [SignalType.BUY_CALL, SignalType.BUY_PUT]:
                    opt_type = "CE" if analysis.signal == SignalType.BUY_CALL else "PE"
                    atm = self.kotak.get_atm_option_details(symbol, opt_type, spot_data.ltp)
                    if not atm:
                        continue

                    rec = self.strategy.evaluate(analysis, symbol, atm)
                    risk_dec = self.risk.evaluate(rec)

                    if risk_dec.approved:
                        buy_req = BuyRequest(
                            symbol=rec.symbol, strike=rec.strike, expiry=atm.get("expiry"),
                            option_type="CALL" if rec.option_type == OptionType.CALL else "PUT",
                            quantity=rec.quantity, stoploss=rec.stoploss, target=rec.target,
                            reason=f"AutoTrade scan: {rec.reason}"
                        )
                        result = self.trade.buy(buy_req)
                        logger.info(f"AutoTrade Order Executed: {result}")
                        break
            except Exception as e:
                err = str(e)
                if "rate_limit" in err.lower() or "429" in err:
                    self._rate_limited_until = datetime.now() + timedelta(minutes=5)
                    logger.warning("Groq rate limit hit. Scanner paused for 5m.")
                else:
                    logger.error(f"AutoTrade scan failed for {symbol}: {e}")


# Singleton instance manager
_autotrade_service = None

def get_autotrade_service() -> AutoTradeService:
    global _autotrade_service
    if _autotrade_service is None:
        _autotrade_service = AutoTradeService()
    return _autotrade_service
