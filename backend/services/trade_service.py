from datetime import datetime
from services.kotak_service import KotakService
from services.charges_service import FnOCharges
from models import Trade, TradeStatus
from schemas import BuyRequest, SellRequest, ExitRequest
from config import get_settings
from database import insert_trade, update_trade, get_trade, get_open_trades, get_all_trades
from logger import setup_logger

logger = setup_logger("trade")


class TradeService:
    def __init__(self, kotak: KotakService) -> None:
        self.kotak = kotak

    def buy(self, request: BuyRequest) -> dict:
        settings = get_settings()
        quantity = request.quantity or settings.default_quantity

        logger.info(f"BUY {request.symbol} {request.strike} {request.option_type} x{quantity}")

        trading_symbol = self._build_trading_symbol(
            request.symbol, request.expiry, request.strike, request.option_type
        )

        # Try to resolve live/mock LTP for entry price
        entry_price = 120.0
        try:
            ot_key = "CE" if request.option_type.upper() in ("CALL", "CE") else "PE"
            search_res = self.kotak.search_scrip(
                exchange_segment="nse_fo",
                symbol=request.symbol,
                expiry=request.expiry,
                option_type=ot_key,
                strike_price=str(int(request.strike))
            )
            contracts = []
            if isinstance(search_res, list):
                contracts = search_res
            elif isinstance(search_res, dict):
                contracts = search_res.get("data", search_res.get("scrip", []))
                if not isinstance(contracts, list):
                    contracts = [contracts] if contracts else []
            
            if contracts:
                token = contracts[0].get("pInstToken", contracts[0].get("instrumentToken", ""))
                if token:
                    quote_resp = self.kotak.get_quotes([{"instrument_token": str(token), "exchange_segment": "nse_fo"}])
                    if quote_resp and isinstance(quote_resp, dict):
                        q_data = quote_resp.get("data", [{}])[0]
                        entry_price = float(q_data.get("ltp", 120.0))
        except Exception as e:
            logger.warning(f"Could not resolve entry price: {e}. Defaulting to 120.0")

        if entry_price <= 0:
            entry_price = 120.0

        stoploss = request.stoploss or round(entry_price * 0.80, 2)
        target = request.target or round(entry_price * 1.40, 2)

        order_response = self.kotak.place_order(
            exchange_segment="nse_fo",
            product="MIS",
            price="0",
            order_type="MKT",
            quantity=str(quantity),
            validity="DAY",
            trading_symbol=trading_symbol,
            transaction_type="B",
        )

        order_id = ""
        if isinstance(order_response, dict):
            order_id = str(order_response.get("nOrdNo", order_response.get("orderId", "")))

        trade_data = {
            "timestamp": datetime.now().isoformat(),
            "symbol": request.symbol,
            "strike": request.strike,
            "expiry": request.expiry,
            "option_type": request.option_type,
            "entry_price": entry_price,
            "exit_price": None,
            "quantity": quantity,
            "stoploss": stoploss,
            "target": target,
            "pnl": 0.0,
            "strategy": "MANUAL" if "Manual" in (request.reason or "") else "AI_SYSTEM",
            "reason": request.reason or "Manual buy order",
            "status": TradeStatus.OPEN,
            "order_id": order_id,
        }
        trade_id = insert_trade(trade_data)

        logger.info(f"Trade created: id={trade_id}, order_id={order_id}, entry={entry_price}")
        return {
            "trade_id": trade_id,
            "order_id": order_id,
            "trading_symbol": trading_symbol,
            "entry_price": entry_price,
            "stoploss": stoploss,
            "target": target,
            "order_response": order_response,
        }

    def sell(self, request: SellRequest) -> dict:
        logger.info(f"SELL order_id={request.order_id}")

        order_response = self.kotak.place_order(
            exchange_segment="nse_fo",
            product="MIS",
            price=str(request.exit_price or 0),
            order_type="MKT",
            quantity="0",
            validity="DAY",
            trading_symbol="",
            transaction_type="S",
        )

        logger.info(f"Sell order placed: {order_response}")
        return {"order_response": order_response}

    def exit_trade(self, request: ExitRequest) -> dict:
        trade = get_trade(request.trade_id)
        if not trade:
            raise ValueError(f"Trade {request.trade_id} not found")

        if trade["status"] != TradeStatus.OPEN:
            raise ValueError(f"Trade {request.trade_id} is not open (status: {trade['status']})")

        logger.info(f"Exiting trade {request.trade_id}: {trade['symbol']}")

        trading_symbol = self._build_trading_symbol(
            trade["symbol"],
            trade.get("expiry", ""),
            trade.get("strike", 0),
            trade.get("option_type", "CE"),
        )

        # Try to resolve live/mock LTP for exit price
        exit_price = 150.0
        try:
            ot_key = "CE" if trade.get("option_type") == "CALL" else "PE"
            search_res = self.kotak.search_scrip(
                exchange_segment="nse_fo",
                symbol=trade["symbol"],
                expiry=trade.get("expiry", ""),
                option_type=ot_key,
                strike_price=str(int(trade.get("strike", 0)))
            )
            contracts = []
            if isinstance(search_res, list):
                contracts = search_res
            elif isinstance(search_res, dict):
                contracts = search_res.get("data", search_res.get("scrip", []))
                if not isinstance(contracts, list):
                    contracts = [contracts] if contracts else []
            
            if contracts:
                token = contracts[0].get("pInstToken", contracts[0].get("instrumentToken", ""))
                if token:
                    quote_resp = self.kotak.get_quotes([{"instrument_token": str(token), "exchange_segment": "nse_fo"}])
                    if quote_resp and isinstance(quote_resp, dict):
                        q_data = quote_resp.get("data", [{}])[0]
                        exit_price = float(q_data.get("ltp", 150.0))
        except Exception as e:
            logger.warning(f"Could not resolve exit price: {e}. Defaulting to 150.0")

        if exit_price <= 0:
            exit_price = 150.0

        order_response = self.kotak.place_order(
            exchange_segment="nse_fo",
            product="MIS",
            price="0",
            order_type="MKT",
            quantity=str(trade["quantity"]),
            validity="DAY",
            trading_symbol=trading_symbol,
            transaction_type="S",
        )

        entry_price = trade.get("entry_price", 0) or 0
        quantity = trade["quantity"]

        # Calculate PnL with charges
        pnl_result = FnOCharges.calculate_net_pnl(entry_price, exit_price, quantity)
        charges = pnl_result["charges"]

        update_trade(request.trade_id, {
            "status": TradeStatus.CLOSED,
            "exit_price": exit_price,
            "pnl": pnl_result["net_pnl"],
            "gross_pnl": pnl_result["gross_pnl"],
            "total_charges": charges["total_charges"],
            "brokerage": charges["brokerage"],
            "stt": charges["stt"],
            "transaction_charges": charges["transaction_charges"],
            "gst": charges["gst"],
            "sebi_fees": charges["sebi_fees"],
            "stamp_duty": charges["stamp_duty"],
            "reason": request.reason or trade.get("reason", ""),
        })

        logger.info(
            f"Trade {request.trade_id} closed | "
            f"Entry: {entry_price:.2f}, Exit: {exit_price:.2f} | "
            f"Gross PnL: ₹{pnl_result['gross_pnl']:.2f} | "
            f"Charges: ₹{pnl_result['charges']['total_charges']:.2f} | "
            f"Net PnL: ₹{pnl_result['net_pnl']:.2f}"
        )
        return {
            "trade_id": request.trade_id,
            "exit_price": exit_price,
            "pnl": pnl_result["net_pnl"],
            "gross_pnl": pnl_result["gross_pnl"],
            "charges": charges,
            "order_response": order_response,
        }

    def modify_stoploss(self, order_id: str, new_sl: float) -> dict:
        logger.info(f"Modifying SL: order_id={order_id}, new_sl={new_sl}")
        response = self.kotak.modify_order(
            order_id=order_id,
            price="0",
            quantity="0",
            trigger_price=str(new_sl),
            order_type="SL-M",
        )
        return {"order_id": order_id, "new_stoploss": new_sl, "response": response}

    def cancel_order(self, order_id: str) -> dict:
        logger.info(f"Cancelling order: {order_id}")
        response = self.kotak.cancel_order(order_id)
        return {"order_id": order_id, "response": response}

    def get_orders(self) -> dict:
        return self.kotak.get_order_report()

    def get_positions(self) -> dict:
        return self.kotak.get_positions()

    def get_history(self, limit: int = 100) -> list[dict]:
        return get_all_trades(limit)

    def get_open(self) -> list[dict]:
        return get_open_trades()

    def _build_trading_symbol(
        self, symbol: str, expiry: str, strike: float, option_type: str
    ) -> str:
        expiry_fmt = expiry.replace("-", "") if expiry else ""
        ot = "CE" if option_type.upper() in ("CALL", "CE") else "PE"
        strike_str = str(int(strike)) if strike else ""
        return f"{symbol}{expiry_fmt}{strike_str}{ot}"
