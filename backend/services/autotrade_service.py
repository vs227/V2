from apscheduler.schedulers.background import BackgroundScheduler
from services.kotak_service import get_kotak_service
from services.market_service import MarketService
from services.llm_ai_service import LLMService
from services.strategy_service import StrategyService
from services.risk_service import RiskService
from services.trade_service import TradeService
from schemas import BuyRequest, ExitRequest
from logger import setup_logger
from datetime import datetime, timedelta
import pytz

logger = setup_logger("autotrade")


class AutoTradeService:
    def __init__(self) -> None:
        self.kotak = get_kotak_service()
        self.market = MarketService(self.kotak)
        self.ai = LLMService()
        self.strategy = StrategyService()
        self.risk = RiskService()
        self.trade = TradeService(self.kotak)

        self.scheduler = BackgroundScheduler()
        self.enabled = False
        self.target_timezone = pytz.timezone("Asia/Kolkata")
        self._rate_limited_until = None  # Rate-limit backoff timestamp
        self.last_analysis = None  # Cache of the last AI decision for the UI drawer

        # Scan every 120 seconds to stay within Groq free-tier token limits
        self.scheduler.add_job(self.run_scan, "interval", seconds=120, id="autotrade_scan_job")
        # Monitor active open positions every 2 seconds for immediate SL/Target exit
        self.scheduler.add_job(self.run_fast_monitor, "interval", seconds=2, id="autotrade_monitor_job")
        # Explicit garbage collection job every 60 seconds to release Python heap memory
        self.scheduler.add_job(self.run_gc, "interval", seconds=60, id="autotrade_gc_job")

        # Start scheduler on init
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("AutoTrade Scheduler started (Scan: 120s, Monitor: 2s, GC: 60s).")

    def run_gc(self) -> None:
        """Explicitly run garbage collection to free unused memory on Render container."""
        import gc
        logger.info("AutoTrade: Running periodic garbage collection...")
        collected = gc.collect()
        logger.info(f"AutoTrade: Garbage collection finished. Cleaned {collected} unreachable objects.")

    def run_fast_monitor(self) -> None:
        """Runs every 2 seconds to check and manage active trades (no LLM tokens used)."""
        if not self.enabled:
            return
        if not self.kotak.is_authenticated:
            return
        self._check_and_manage_trades()

    def enable(self) -> None:
        self.enabled = True
        logger.info("AutoTrade Mode ENABLED.")

    def disable(self) -> None:
        self.enabled = False
        logger.info("AutoTrade Mode DISABLED.")

    @property
    def is_enabled(self) -> bool:
        return self.enabled

    def is_market_hours(self) -> bool:
        """Check if current time is within Indian market hours (9:15 AM to 3:30 PM, Monday-Friday)"""
        now = datetime.now(self.target_timezone)

        # Monday = 0, Sunday = 6
        if now.weekday() >= 5:
            return False

        start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
        end_time = now.replace(hour=15, minute=30, second=0, microsecond=0)

        return start_time <= now <= end_time

    def _check_and_manage_trades(self) -> None:
        """Checks all open trades and auto-exits if SL or Target are hit."""
        open_trades = self.trade.get_open()
        if not open_trades:
            return

        logger.info(f"AutoTrade: Monitoring {len(open_trades)} active trade(s)")
        for ot in open_trades:
            trade_id = ot["id"]
            symbol = ot["symbol"]
            strike = ot["strike"]
            option_type = ot["option_type"]
            entry_price = ot["entry_price"]
            stoploss = ot["stoploss"]
            target = ot["target"]
            quantity = ot["quantity"]

            # Try to resolve LTP of the option contract
            ot_key = "CE" if option_type.upper() in ("CALL", "CE") else "PE"
            try:
                search_res = self.kotak.search_scrip(
                    exchange_segment="nse_fo",
                    symbol=symbol,
                    expiry=ot.get("expiry", ""),
                    option_type=ot_key,
                    strike_price=str(int(strike))
                )
                contracts = []
                if isinstance(search_res, list):
                    contracts = search_res
                elif isinstance(search_res, dict):
                    contracts = search_res.get("data", search_res.get("scrip", []))
                    if not isinstance(contracts, list):
                        contracts = [contracts] if contracts else []

                if not contracts:
                    continue

                token = contracts[0].get("pInstToken", contracts[0].get("instrumentToken", ""))
                if not token:
                    continue

                quote_resp = self.kotak.get_quotes([{"instrument_token": str(token), "exchange_segment": "nse_fo"}])
                if not quote_resp or not isinstance(quote_resp, dict):
                    continue

                q_data = quote_resp.get("data", [{}])[0]
                ltp = float(q_data.get("ltp", 0.0))

                if ltp <= 0:
                    continue

                logger.info(f"AutoTrade Trade #{trade_id} ({symbol} {strike} {ot_key}): LTP={ltp} | Entry={entry_price} | SL={stoploss} | Tgt={target}")

                # Check SL/Target breach
                if ltp >= target:
                    logger.info(f"AutoTrade: Trade #{trade_id} Target hit! Exiting at {ltp}.")
                    self.trade.exit_trade(ExitRequest(trade_id=trade_id, reason="Auto-Exit: Target hit"))
                elif ltp <= stoploss:
                    logger.info(f"AutoTrade: Trade #{trade_id} Stoploss hit! Exiting at {ltp}.")
                    self.trade.exit_trade(ExitRequest(trade_id=trade_id, reason="Auto-Exit: Stoploss hit"))

            except Exception as e:
                logger.error(f"Error checking trade #{trade_id} in background: {e}")

    def run_scan(self) -> None:
        if not self.enabled:
            return

        # Rate-limit backoff: skip scanning if we're in a cooldown period
        if self._rate_limited_until and datetime.now() < self._rate_limited_until:
            remaining = int((self._rate_limited_until - datetime.now()).total_seconds())
            logger.info(f"AutoTrade scan paused: Groq rate-limit cooldown ({remaining}s remaining)")
            return

        logger.info("Starting automated market scan...")

        if not self.kotak.is_authenticated:
            logger.warning("AutoTrade scan skipped: Kotak Neo is not authenticated.")
            return

        # Check market hours (optional but recommended for real trading)
        if not self.is_market_hours():
            logger.info("AutoTrade scan: Outside regular IST hours, running in Simulation mode.")

        try:
            # 1. Open trade management is now handled every 2 seconds by run_fast_monitor
            # 2. Check if we can enter a new trade
            open_trades = self.trade.get_open()
            max_open = 1  # We can configure this
            if len(open_trades) >= max_open:
                logger.info(f"AutoTrade: Already at max open trades limit ({max_open}). Skipping scan.")
                return

            # Fetch VIX once
            vix = self.market.get_india_vix()

            for symbol in ["NIFTY", "BANKNIFTY"]:
                # Check if there is already an open trade for this specific symbol
                has_active = any(t.get("symbol") == symbol for t in open_trades)
                if has_active:
                    logger.info(f"AutoTrade: Already have active trade for {symbol}. Skipping.")
                    continue

                logger.info(f"AutoTrade: Scanning {symbol}...")

                # Fetch spot OHLC
                nifty_ohlc = self.market.get_nifty_ohlc()
                banknifty_ohlc = self.market.get_banknifty_ohlc()
                spot_data = nifty_ohlc if symbol == "NIFTY" else banknifty_ohlc

                if spot_data.ltp <= 0:
                    logger.warning(f"AutoTrade: Invalid spot price for {symbol}. Skipping.")
                    continue

                # Fetch option chain for index
                option_chain = self.market.get_option_chain(symbol)

                # Run AI Analysis
                analysis = self.ai.analyze_with_llm(nifty_ohlc, banknifty_ohlc, option_chain, vix)
                logger.info(f"AutoTrade: {symbol} Signal={analysis.signal.value} (Confidence={analysis.confidence}%)")

                # Store details for frontend drawer
                self.last_analysis = {
                    "trend": analysis.trend.value if hasattr(analysis.trend, "value") else str(analysis.trend),
                    "signal": analysis.signal.value if hasattr(analysis.signal, "value") else str(analysis.signal),
                    "confidence": int(analysis.confidence),
                    "reason": str(analysis.reason),
                    "timestamp": datetime.now().isoformat(),
                    "symbol": symbol,
                    "vix": float(vix.get("vix")) if (vix and vix.get("vix") is not None) else 15.0,
                    "spot_price": float(spot_data.ltp)
                }

                # Clear rate-limit flag on successful LLM call
                self._rate_limited_until = None

                # Lower the required confidence slightly to 60% for a higher trigger rate in simulation
                if analysis.signal in ["BUY_CALL", "BUY_PUT"] and analysis.confidence >= 60:
                    # Find ATM Option details
                    opt_type = "CE" if analysis.signal == "BUY_CALL" else "PE"
                    atm_details = self.market.get_atm_option_details(symbol, opt_type, spot_data.ltp)

                    if not atm_details or atm_details.get("ltp", 0) <= 0:
                        logger.warning(f"AutoTrade: Could not find valid ATM option for {symbol}")
                        continue

                    # Evaluate Strategy Setup
                    rec = self.strategy.evaluate(analysis, symbol, atm_details)

                    # Evaluate Risk Parameters
                    risk_dec = self.risk.evaluate(rec)

                    if risk_dec.approved:
                        logger.info(f"AutoTrade: RISK APPROVED. Placing trade for {atm_details['trading_symbol']}")
                        buy_req = BuyRequest(
                            symbol=symbol,
                            strike=rec.strike,
                            expiry=atm_details.get("expiry", ""),
                            option_type="CALL" if rec.option_type == "CALL" else "PUT",
                            quantity=rec.quantity,
                            stoploss=rec.stoploss,
                            target=rec.target,
                            reason=f"Autotrade Signal: {rec.reason}"
                        )
                        result = self.trade.buy(buy_req)
                        logger.info(f"AutoTrade: Order placed successfully: {result}")

                        # Break loop since we filled our max trades slot
                        break
                    else:
                        logger.info(f"AutoTrade: Risk REJECTED for {symbol}: {risk_dec.reason}")

        except Exception as e:
            error_str = str(e)
            # Detect Groq rate-limit errors and enter cooldown
            if "rate_limit" in error_str.lower() or "429" in error_str:
                cooldown_minutes = 5
                self._rate_limited_until = datetime.now() + timedelta(minutes=cooldown_minutes)
                logger.warning(f"AutoTrade: Groq rate limit hit. Pausing LLM scans for {cooldown_minutes} minutes.")
            else:
                logger.error(f"AutoTrade Scan failed: {e}")


# Singleton instance
_autotrade_service = None


def get_autotrade_service() -> AutoTradeService:
    global _autotrade_service
    if _autotrade_service is None:
        _autotrade_service = AutoTradeService()
    return _autotrade_service
