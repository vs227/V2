from services.kotak_service import KotakService
from models import MarketData
from logger import setup_logger
from datetime import datetime

logger = setup_logger("market")

NIFTY_TOKEN = {"instrument_token": "26000", "exchange_segment": "nse_cm"}
BANKNIFTY_TOKEN = {"instrument_token": "26009", "exchange_segment": "nse_cm"}
INDIA_VIX_TOKEN = {"instrument_token": "26017", "exchange_segment": "nse_cm"}


class MarketService:
    def __init__(self, kotak: KotakService) -> None:
        self.kotak = kotak

    def _parse_quote(self, symbol: str, response: dict) -> MarketData:
        data = response if isinstance(response, dict) else {}
        return MarketData(
            symbol=symbol,
            ltp=float(data.get("ltp", 0)),
            open=float(data.get("open", 0)),
            high=float(data.get("high", 0)),
            low=float(data.get("low", 0)),
            close=float(data.get("close", data.get("previous_close", 0))),
            volume=int(data.get("volume", data.get("total_quantity_traded", 0))),
            timestamp=datetime.now(),
        )

    def get_nifty_price(self) -> MarketData:
        response = self.kotak.get_quotes([NIFTY_TOKEN], quote_type="ltp")
        data = self._extract_first_quote(response)
        return self._parse_quote("NIFTY", data)

    def get_banknifty_price(self) -> MarketData:
        response = self.kotak.get_quotes([BANKNIFTY_TOKEN], quote_type="ltp")
        data = self._extract_first_quote(response)
        return self._parse_quote("BANKNIFTY", data)

    def get_nifty_ohlc(self) -> MarketData:
        response = self.kotak.get_quotes([NIFTY_TOKEN], quote_type="ohlc")
        data = self._extract_first_quote(response)
        return self._parse_quote("NIFTY", data)

    def get_banknifty_ohlc(self) -> MarketData:
        response = self.kotak.get_quotes([BANKNIFTY_TOKEN], quote_type="ohlc")
        data = self._extract_first_quote(response)
        return self._parse_quote("BANKNIFTY", data)

    def get_option_chain(self, symbol: str = "NIFTY", expiry: str = "") -> dict:
        logger.info(f"Fetching option chain for {symbol}")
        try:
            # 1. Fetch index spot price
            spot_price = 0.0
            if symbol == "NIFTY":
                spot_price = self.get_nifty_price().ltp
            elif symbol == "BANKNIFTY":
                spot_price = self.get_banknifty_price().ltp

            if spot_price <= 0:
                spot_price = 24350.0 if symbol == "NIFTY" else 52400.0

            # 2. Search scrips (contracts)
            results = self.kotak.search_scrip(
                exchange_segment="nse_fo",
                symbol=symbol,
                expiry=expiry,
                option_type="",
                strike_price="",
            )
            
            contracts = []
            if isinstance(results, dict):
                contracts = results.get("data", results.get("scrip", []))
            elif isinstance(results, list):
                contracts = results

            if not isinstance(contracts, list) or not contracts:
                return {"data": [], "spot_price": spot_price}

            # 3. Filter contracts with valid strikes
            valid_contracts = []
            for c in contracts:
                try:
                    strike_val = float(c.get("strike", c.get("pStrikePrice", 0)))
                    opt_type = c.get("option_type", c.get("pOptionType", ""))
                    if strike_val > 0 and opt_type in ("CE", "PE"):
                        valid_contracts.append(c)
                except (ValueError, TypeError):
                    continue

            if not valid_contracts:
                return {"data": [], "spot_price": spot_price}

            # 4. Find the closest 10 strikes
            strikes = list(set(float(c.get("strike")) for c in valid_contracts))
            strikes.sort(key=lambda x: abs(x - spot_price))
            selected_strikes = sorted(strikes[:10])

            # Filter contracts belonging to the selected strikes
            chain_contracts = [c for c in valid_contracts if float(c.get("strike")) in selected_strikes]

            # 5. Fetch quotes for these contracts
            tokens = []
            for c in chain_contracts:
                token = c.get("instrumentToken", c.get("pInstToken", ""))
                seg = c.get("exchangeSegment", c.get("pExchSeg", "nse_fo"))
                if token:
                    tokens.append({"instrument_token": str(token), "exchange_segment": seg})

            quotes_data = {}
            if tokens:
                try:
                    quotes_resp = self.kotak.get_quotes(tokens, quote_type="ohlc")
                    q_list = []
                    if isinstance(quotes_resp, dict):
                        q_list = quotes_resp.get("data", [])
                    elif isinstance(quotes_resp, list):
                        q_list = quotes_resp
                    
                    for q in q_list:
                        tk = str(q.get("instrument_token", ""))
                        if tk:
                            quotes_data[tk] = q
                except Exception as qe:
                    logger.warning(f"Failed to fetch quotes for option chain: {qe}")

            # 6. Group CE and PE for each strike
            strike_map = {}
            for s in selected_strikes:
                strike_map[s] = {"strike": s, "CE": None, "PE": None}

            for c in chain_contracts:
                strike = float(c.get("strike"))
                opt_type = c.get("option_type")
                token = c.get("instrumentToken", c.get("pInstToken", ""))
                
                # Fetch quote if available, else mock/default
                quote = quotes_data.get(str(token), {})
                
                # Derive mock premium if quote missing
                default_premium = 120.0 if symbol == "NIFTY" else 280.0
                ltp_val = float(quote.get("ltp", quote.get("last_price", default_premium)))
                
                details = {
                    "symbol": c.get("tradingSymbol", c.get("pTrdSym", "")),
                    "token": token,
                    "expiry": c.get("expiry", c.get("pExpiryDate", "")),
                    "ltp": ltp_val,
                    "change": float(quote.get("change", 0.0)),
                    "volume": int(quote.get("volume", quote.get("total_quantity_traded", 0))),
                    "oi": int(c.get("call_oi", c.get("put_oi", quote.get("open_interest", 1000000))))
                }
                
                if opt_type == "CE":
                    strike_map[strike]["CE"] = details
                elif opt_type == "PE":
                    strike_map[strike]["PE"] = details

            # Build list sorted by strike
            chain_list = [strike_map[s] for s in selected_strikes]

            return {
                "data": chain_list,
                "spot_price": spot_price,
                "symbol": symbol
            }
        except Exception as e:
            logger.error(f"Option chain construction failed: {e}")
            return {"data": [], "spot_price": 0.0}

    def get_india_vix(self) -> dict:
        try:
            response = self.kotak.get_quotes([INDIA_VIX_TOKEN], quote_type="ltp")
            data = self._extract_first_quote(response)
            return {"vix": float(data.get("ltp", 0))}
        except Exception as e:
            logger.warning(f"India VIX unavailable: {e}")
            return {"vix": None, "error": str(e)}

    def get_market_overview(self) -> dict:
        tokens = [NIFTY_TOKEN, BANKNIFTY_TOKEN, INDIA_VIX_TOKEN]
        try:
            # Batch fetch all index quotes in a single call to Kotak Neo
            response = self.kotak.get_quotes(tokens, quote_type="ohlc")
            
            # Extract data list
            data_list = []
            if isinstance(response, dict):
                data_list = response.get("data", [])
            elif isinstance(response, list):
                data_list = response
                
            nifty_data = {}
            banknifty_data = {}
            vix_data = {}
            
            for item in data_list:
                tk = str(item.get("instrument_token", ""))
                if tk == NIFTY_TOKEN["instrument_token"]:
                    nifty_data = item
                elif tk == BANKNIFTY_TOKEN["instrument_token"]:
                    banknifty_data = item
                elif tk == INDIA_VIX_TOKEN["instrument_token"]:
                    vix_data = item
                    
            nifty = self._parse_quote("NIFTY", nifty_data)
            banknifty = self._parse_quote("BANKNIFTY", banknifty_data)
            vix_ltp = float(vix_data.get("ltp", 0.0)) if vix_data else 15.0
            
            return {
                "nifty": nifty.model_dump(mode="json"),
                "banknifty": banknifty.model_dump(mode="json"),
                "india_vix": {"vix": vix_ltp},
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to batch fetch market overview: {e}. Falling back to sequential calls.")
            nifty = self.get_nifty_ohlc()
            banknifty = self.get_banknifty_ohlc()
            vix = self.get_india_vix()
            return {
                "nifty": nifty.model_dump(mode="json"),
                "banknifty": banknifty.model_dump(mode="json"),
                "india_vix": vix,
                "timestamp": datetime.now().isoformat(),
            }

    def get_atm_option_details(self, symbol: str, option_type: str, spot_price: float) -> dict:
        if symbol == "NIFTY":
            strike = round(spot_price / 50) * 50
        elif symbol == "BANKNIFTY":
            strike = round(spot_price / 100) * 100
        else:
            strike = round(spot_price)

        ot_key = "CE" if option_type.upper() in ("CALL", "CE") else "PE"
        logger.info(f"Finding ATM option for {symbol}: spot={spot_price}, strike={strike}, type={ot_key}")

        try:
            results = self.kotak.search_scrip(
                exchange_segment="nse_fo",
                symbol=symbol,
                expiry="",
                option_type=ot_key,
                strike_price=str(strike),
            )
            contracts = []
            if isinstance(results, list):
                contracts = results
            elif isinstance(results, dict):
                contracts = results.get("data", results.get("scrip", []))
                if not isinstance(contracts, list):
                    contracts = [contracts] if contracts else []

            if not contracts:
                logger.warning(f"No option contracts found for {symbol} strike {strike}")
                return {}

            # Pick the first matching contract
            contract = contracts[0]
            trading_symbol = contract.get("pTrdSym", contract.get("tradingSymbol", ""))
            token = contract.get("pInstToken", contract.get("instrumentToken", ""))

            # Fetch live quote to get the actual premium price
            ltp = 0.0
            expiry = contract.get("pExpiryDate", contract.get("expiry", ""))
            if token:
                quote_resp = self.kotak.get_quotes([{"instrument_token": str(token), "exchange_segment": "nse_fo"}])
                quote_data = self._extract_first_quote(quote_resp)
                ltp = float(quote_data.get("ltp", 0.0))

            return {
                "trading_symbol": trading_symbol,
                "instrument_token": token,
                "strike": float(strike),
                "option_type": ot_key,
                "ltp": ltp,
                "expiry": expiry
            }
        except Exception as e:
            logger.error(f"Failed to fetch ATM option details: {e}")
            return {}

    def _extract_first_quote(self, response: dict) -> dict:
        if isinstance(response, list) and len(response) > 0:
            return response[0]
        if isinstance(response, dict):
            data = response.get("data", response)
            if isinstance(data, list) and len(data) > 0:
                return data[0]
            return data
        return {}
