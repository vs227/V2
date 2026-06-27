from config import get_settings
from logger import setup_logger
from typing import Optional
import random

logger = setup_logger("kotak")

try:
    from neo_api_client import NeoAPI
    HAS_SDK = True
except ImportError:
    HAS_SDK = False
    logger.warning("neo_api_client SDK not found. Defaulting to Paper Trading Mode.")


class KotakService:
    def __init__(self) -> None:
        settings = get_settings()
        self._authenticated = False
        self._real_authenticated = False
        self._scrip_cache = {}

        # Always initialize self.client if SDK is present to fetch real market data/quotes
        if HAS_SDK:
            try:
                self.client = NeoAPI(
                    environment="prod",
                    access_token=None,
                    neo_fin_key=None,
                    consumer_key=settings.kotak_consumer_key,
                )
                logger.info("Kotak Neo client SDK initialized (Hybrid Paper/Live)")
            except Exception as e:
                logger.error(f"Failed to initialize NeoAPI: {e}")
                self.client = None
        else:
            self.client = None
            logger.info("Kotak Neo client SDK not found. Running in fully offline mock mode.")

    @property
    def is_paper(self) -> bool:
        settings = get_settings()
        return settings.paper_trading or not HAS_SDK

    def login(self, totp: str) -> dict:
        if self.client:
            settings = get_settings()
            logger.info("Logging in to Kotak Neo via TOTP (Real Connection)")
            if totp == "123456":
                logger.info("Login (Simulated Bypass): Authenticating with dummy TOTP")
                self._authenticated = True
                self._real_authenticated = False
                return {
                    "login": {"status": "success", "message": "Authenticated in Simulation mode"},
                    "validate": {"status": "success", "message": "MPIN Validated in Simulation mode"}
                }
            try:
                login_resp = self.client.totp_login(
                    mobile_number=settings.kotak_mobile_number,
                    ucc=settings.kotak_ucc,
                    totp=totp,
                )
                logger.info(f"TOTP login response: {login_resp}")

                validate_resp = self.client.totp_validate(mpin=settings.kotak_mpin)
                logger.info(f"TOTP validate response: {validate_resp}")

                self._authenticated = True
                self._real_authenticated = True
                return {"login": login_resp, "validate": validate_resp}
            except Exception as e:
                logger.error(f"Login failed: {e}")
                raise
        else:
            logger.info("Login (Simulated): Authenticating with dummy TOTP (Offline Mode)")
            self._authenticated = True
            self._real_authenticated = False
            return {
                "login": {"status": "success", "message": "Authenticated in Simulation mode"},
                "validate": {"status": "success", "message": "MPIN Validated in Simulation mode"}
            }

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated or self._real_authenticated

    def get_quotes(self, instrument_tokens: list[dict], quote_type: str = "ltp") -> dict:
        logger.info(f"Fetching quotes: {instrument_tokens}, type={quote_type}")
        
        # 1. Try real API call if logged in
        if self.client and self._real_authenticated:
            try:
                response = self.client.quotes(
                    instrument_tokens=instrument_tokens,
                    quote_type=quote_type,
                )
                logger.info("Quotes received from Kotak Neo API")
                return response
            except Exception as e:
                logger.error(f"Failed to fetch quotes from Kotak Neo: {e}. Falling back to mocks.")
                
        # 2. Fallback mock quotes generator
        data = []
        for token_info in instrument_tokens:
            token = str(token_info.get("instrument_token", ""))
            # Mock Nifty
            if token == "26000":
                data.append({
                    "instrument_token": token,
                    "ltp": "24350.50", "open": "24300.00", "high": "24400.00",
                    "low": "24280.00", "close": "24310.20", "volume": "520000",
                    "previous_close": "24310.20", "total_quantity_traded": "520000"
                })
            # Mock BankNifty
            elif token == "26009":
                data.append({
                    "instrument_token": token,
                    "ltp": "52450.00", "open": "52200.00", "high": "52600.00",
                    "low": "52150.00", "close": "52300.00", "volume": "380000",
                    "previous_close": "52300.00", "total_quantity_traded": "380000"
                })
            # Mock India VIX
            elif token == "26017":
                data.append({
                    "instrument_token": token,
                    "ltp": "14.25", "open": "14.00", "high": "14.50",
                    "low": "13.80", "close": "14.10", "volume": "0"
                })
            else:
                # Mock option premium quote
                base_premium = 120.0
                try:
                    parts = token.split("_")
                    if len(parts) == 3:
                        sym, strike_str, ot = parts
                        strike_val = float(strike_str)
                        spot_val = 24350.0 if sym == "NIFTY" else 52450.0
                        
                        if ot == "CE":
                            intrinsic = max(0.0, spot_val - strike_val)
                        else:
                            intrinsic = max(0.0, strike_val - spot_val)
                        
                        distance = abs(spot_val - strike_val)
                        time_value = max(10.0, 150.0 - (distance * 0.1))
                        base_premium = intrinsic + time_value + random.uniform(-5, 5)
                        if sym == "NIFTY":
                            base_premium = base_premium * 0.5
                except Exception:
                    if "NIFTY" in token:
                        base_premium = 120.0 + random.uniform(-15, 15)
                    elif "BANKNIFTY" in token:
                        base_premium = 280.0 + random.uniform(-30, 30)
                
                vol_base = 50000
                try:
                    parts = token.split("_")
                    if len(parts) == 3:
                        distance = abs(float(parts[1]) - (24350.0 if parts[0] == "NIFTY" else 52450.0))
                        vol_base = max(1000, int(120000 - (distance * 100)))
                except Exception:
                    pass

                data.append({
                    "instrument_token": token,
                    "ltp": str(round(base_premium, 2)),
                    "open": str(round(base_premium * 0.95, 2)),
                    "high": str(round(base_premium * 1.15, 2)),
                    "low": str(round(base_premium * 0.85, 2)),
                    "close": str(round(base_premium * 0.98, 2)),
                    "volume": str(vol_base),
                    "previous_close": str(round(base_premium * 0.98, 2))
                })
        return {"data": data}

    def search_scrip(
        self,
        exchange_segment: str,
        symbol: str,
        expiry: str = "",
        option_type: str = "",
        strike_price: str = "",
    ) -> dict:
        logger.info(f"Searching scrip: {symbol} on {exchange_segment} (Paper={self.is_paper})")
        
        # 1. Check cache first for real calls
        import time
        cache_key = (exchange_segment, symbol, expiry, option_type, strike_price)
        now = time.time()
        if cache_key in self._scrip_cache:
            ts, cached_res = self._scrip_cache[cache_key]
            if now - ts < 3600:  # 1 hour TTL
                logger.info(f"Returning cached scrip search for {symbol}")
                return cached_res
                
        # 2. Try real API call if logged in
        if self.client and self._real_authenticated:
            try:
                response = self.client.search_scrip(
                    exchange_segment=exchange_segment,
                    symbol=symbol,
                    expiry=expiry,
                    option_type=option_type,
                    strike_price=strike_price,
                )
                logger.info(f"Scrip search complete: {symbol} (Real data)")
                self._scrip_cache[cache_key] = (now, response)
                return response
            except Exception as e:
                logger.error(f"Scrip search failed: {e}. Falling back to mocks.")
                
        # 3. Fallback mock scrip search
        if strike_price:
            opt_key = option_type if option_type else "CE"
            exp_str = expiry if expiry else "2026-07-02"
            tradingsymbol = f"{symbol}{exp_str.replace('-', '')}{strike_price}{opt_key}"
            token = f"{symbol}_{strike_price}_{opt_key}"
            return {
                "data": [
                    {
                        "pTrdSym": tradingsymbol,
                        "tradingSymbol": tradingsymbol,
                        "pInstToken": token,
                        "instrumentToken": token,
                        "pExpiryDate": exp_str,
                        "expiry": exp_str,
                        "strike": float(strike_price),
                        "option_type": opt_key,
                    }
                ]
            }
            
        strikes = []
        if symbol == "NIFTY":
            atm = 24350
            step = 50
        elif symbol == "BANKNIFTY":
            atm = 52400
            step = 100
        else:
            atm = 1000
            step = 10
            
        contracts = []
        for i in range(-5, 6):
            strike = atm + (i * step)
            for ot in ["CE", "PE"]:
                ts = f"{symbol}26JUL{strike}{ot}"
                contracts.append({
                    "pTrdSym": ts,
                    "tradingSymbol": ts,
                    "pInstToken": f"{symbol}_{strike}_{ot}",
                    "instrumentToken": f"{symbol}_{strike}_{ot}",
                    "pExpiryDate": "2026-07-02",
                    "expiry": "2026-07-02",
                    "strike": float(strike),
                    "option_type": ot,
                    "call_oi": 1000000 + i * 50000 if ot == "CE" else 900000 - i * 50000,
                    "put_oi": 900000 + i * 50000 if ot == "PE" else 1100000 - i * 50000,
                })
        return {"data": contracts}

    def get_scrip_master(self, exchange_segment: str = "") -> dict:
        logger.info(f"Fetching scrip master: {exchange_segment or 'ALL'}")
        if self.is_paper:
            return {"status": "success", "message": "Scrip master simulated"}
        try:
            if exchange_segment:
                return self.client.scrip_master(exchange_segment=exchange_segment)
            return self.client.scrip_master()
        except Exception as e:
            logger.error(f"Scrip master failed: {e}")
            raise

    def place_order(
        self,
        exchange_segment: str,
        product: str,
        price: str,
        order_type: str,
        quantity: str,
        validity: str,
        trading_symbol: str,
        transaction_type: str,
        amo: str = "NO",
        disclosed_quantity: str = "0",
        market_protection: str = "0",
        trigger_price: str = "0",
        tag: Optional[str] = None,
    ) -> dict:
        logger.info(
            f"Placing order (Paper={self.is_paper}): {trading_symbol}, {transaction_type}, "
            f"qty={quantity}, type={order_type}, price={price}"
        )
        if self.is_paper:
            mock_id = f"MOCK_ORD_{random.randint(1000000, 9999999)}"
            return {
                "status": "success",
                "orderId": mock_id,
                "nOrdNo": mock_id,
                "message": "Simulated order placed successfully"
            }

        try:
            response = self.client.place_order(
                exchange_segment=exchange_segment,
                product=product,
                price=price,
                order_type=order_type,
                quantity=quantity,
                validity=validity,
                trading_symbol=trading_symbol,
                transaction_type=transaction_type,
                amo=amo,
                disclosed_quantity=disclosed_quantity,
                market_protection=market_protection,
                trigger_price=trigger_price,
                tag=tag,
            )
            logger.info(f"Order placed: {response}")
            return response
        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            raise

    def modify_order(
        self,
        order_id: str,
        price: str,
        quantity: str,
        disclosed_quantity: str = "0",
        trigger_price: str = "0",
        validity: str = "DAY",
        order_type: str = "L",
    ) -> dict:
        logger.info(f"Modifying order: {order_id}")
        if self.is_paper:
            return {"status": "success", "orderId": order_id, "message": "Simulated order modification success"}
        try:
            response = self.client.modify_order(
                order_id=order_id,
                price=price,
                quantity=quantity,
                disclosed_quantity=disclosed_quantity,
                trigger_price=trigger_price,
                validity=validity,
                order_type=order_type,
            )
            logger.info(f"Order modified: {response}")
            return response
        except Exception as e:
            logger.error(f"Order modification failed: {e}")
            raise

    def cancel_order(self, order_id: str, amo: str = "NO") -> dict:
        logger.info(f"Cancelling order: {order_id}")
        if self.is_paper:
            return {"status": "success", "orderId": order_id, "message": "Simulated order cancellation success"}
        try:
            response = self.client.cancel_order(order_id=order_id, amo=amo, isVerify=True)
            logger.info(f"Order cancelled: {response}")
            return response
        except Exception as e:
            logger.error(f"Order cancellation failed: {e}")
            raise

    def get_order_report(self) -> dict:
        logger.info("Fetching order report")
        if self.is_paper:
            return {"data": []}
        try:
            response = self.client.order_report()
            logger.info("Order report fetched")
            return response
        except Exception as e:
            logger.error(f"Failed to fetch order report: {e}")
            raise

    def get_order_history(self, order_id: str) -> dict:
        logger.info(f"Fetching order history: {order_id}")
        if self.is_paper:
            return {"data": []}
        try:
            return self.client.order_history(order_id=order_id)
        except Exception as e:
            logger.error(f"Failed to fetch order history: {e}")
            raise

    def get_trade_report(self, order_id: str = "") -> dict:
        logger.info("Fetching trade report")
        if self.is_paper:
            return {"data": []}
        try:
            if order_id:
                return self.client.trade_report(order_id=order_id)
            return self.client.trade_report()
        except Exception as e:
            logger.error(f"Failed to fetch trade report: {e}")
            raise

    def get_positions(self) -> dict:
        logger.info("Fetching positions")
        if self.is_paper:
            from database import get_open_trades
            open_trades = get_open_trades()
            positions_list = []
            for t in open_trades:
                strike_str = str(int(t.get("strike", 0)))
                opt_type = "CE" if t.get("option_type") == "CALL" else "PE"
                symbol = t.get("symbol")
                expiry = t.get("expiry")
                
                # Default mock token ID if API is offline
                ts = f"{symbol}26JUL{strike_str}{opt_type}"
                ltp = t.get("entry_price") or 120.0
                
                # Fetch real-time price from Kotak Neo if connected
                if self.client and self.is_authenticated and self._real_authenticated:
                    try:
                        search_res = self.search_scrip(
                            exchange_segment="nse_fo",
                            symbol=symbol,
                            expiry=expiry,
                            option_type=opt_type,
                            strike_price=strike_str
                        )
                        contracts = []
                        if isinstance(search_res, list):
                            contracts = search_res
                        elif isinstance(search_res, dict):
                            contracts = search_res.get("data", search_res.get("scrip", []))
                            if not isinstance(contracts, list):
                                contracts = [contracts] if contracts else []
                        
                        if contracts:
                            contract = contracts[0]
                            ts = contract.get("pTrdSym", contract.get("tradingSymbol", ts))
                            token = contract.get("pInstToken", contract.get("instrumentToken", ""))
                            if token:
                                quote_resp = self.get_quotes([{"instrument_token": str(token), "exchange_segment": "nse_fo"}])
                                if quote_resp and isinstance(quote_resp, dict):
                                    q_data = quote_resp.get("data", [{}])[0]
                                    ltp = float(q_data.get("ltp", ltp))
                    except Exception as e:
                        logger.warning(f"Could not resolve live price for open position: {e}")

                entry_price = t.get("entry_price") or 100.0
                qty = t.get("quantity", 0)
                pnl = round((ltp - entry_price) * qty, 2)
                
                positions_list.append({
                    "tradingSymbol": ts,
                    "symbol": symbol,
                    "qty": str(qty),
                    "buyAvg": str(entry_price),
                    "lastPrice": str(ltp),
                    "pnl": str(pnl),
                    "segment": "nse_fo",
                    "product": "MIS",
                })
            return {"data": positions_list}

        try:
            response = self.client.positions()
            logger.info("Positions fetched")
            return response
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            raise

    def get_holdings(self) -> dict:
        logger.info("Fetching holdings")
        if self.client and self._real_authenticated:
            try:
                return self.client.holdings()
            except Exception as e:
                logger.error(f"Failed to fetch holdings: {e}")
        return {"data": []}

    def get_limits(self, segment: str = "ALL", exchange: str = "ALL", product: str = "ALL") -> dict:
        logger.info(f"Fetching limits: segment={segment}, exchange={exchange} (Paper={self.is_paper})")
        if self.is_paper:
            from database import get_closed_trades, get_open_trades
            starting_capital = 20000.00
            
            # Sum up closed trade PnLs
            try:
                closed = get_closed_trades()
                realized_pnl = sum(float(t.get("pnl", 0.0)) for t in closed)
            except Exception:
                realized_pnl = 0.0

            # Calculate current capital balance
            current_capital = starting_capital + realized_pnl
            
            # Deduct initial cost (margin) of active open positions
            margin_used = 0.0
            try:
                open_trades = get_open_trades()
                for t in open_trades:
                    # In option buying, the margin blocked is the full premium cost (entry * quantity)
                    margin_used += float(t.get("entry_price", 0.0)) * int(t.get("quantity", 0))
            except Exception:
                pass
                
            available_capital = max(0.0, current_capital - margin_used)
            
            return {
                "Net": f"{available_capital:.2f}",
                "data": {
                    "Net": f"{available_capital:.2f}",
                    "margin_used": f"{margin_used:.2f}",
                    "realized_pnl": f"{realized_pnl:.2f}",
                    "total_capital": f"{current_capital:.2f}"
                }
            }
        try:
            return self.client.limits(segment=segment, exchange=exchange, product=product)
        except Exception as e:
            logger.error(f"Failed to fetch limits: {e}")
            raise

    def get_margin_required(
        self,
        exchange_segment: str,
        price: str,
        order_type: str,
        product: str,
        quantity: str,
        instrument_token: str,
        transaction_type: str,
    ) -> dict:
        logger.info(f"Calculating margin: token={instrument_token}, qty={quantity}")
        if self.client and self._real_authenticated:
            try:
                return self.client.margin_required(
                    exchange_segment=exchange_segment,
                    price=price,
                    order_type=order_type,
                    product=product,
                    quantity=quantity,
                    instrument_token=instrument_token,
                    transaction_type=transaction_type,
                )
            except Exception as e:
                logger.error(f"Margin calculation failed: {e}. Falling back to estimate.")
        
        # Estimate: for option buying, margin is premium * qty (assume base premium 120 if price is 0/market)
        pr = float(price) if (price and price != "0") else 120.0
        est_margin = pr * float(quantity)
        return {"margin_required": f"{est_margin:.2f}"}

    def logout(self) -> None:
        logger.info("Logging out from Kotak Neo")
        if self.is_paper:
            self._authenticated = False
            return
        try:
            self.client.logout()
            self._authenticated = False
        except Exception as e:
            logger.error(f"Logout failed: {e}")


from functools import lru_cache

@lru_cache
def get_kotak_service() -> KotakService:
    return KotakService()
