
from logger import setup_logger

logger = setup_logger("charges")


class FnOCharges:
    """
    Calculates realistic NSE F&O charges for options trading (2025-2026 rates)
    """

    # Brokerage (example: flat Rs. 20 per order, or free - adjust to your broker!)
    BROKERAGE_PER_ORDER = 20.0

    # STT on Options (0.0625% of premium for buy+sell? Wait no - STT is 0.0625% of turnover only on sell side for intraday options!)
    STT_RATE = 0.000625  # 0.0625%

    # Transaction Charges (NSE): 0.005% of turnover (both sides)
    NSE_TXN_CHARGES = 0.00005

    # GST: 18% on (brokerage + txn charges)
    GST_RATE = 0.18

    # SEBI Turnover Fees: Rs. 10 per crore (0.00001%)
    SEBI_FEES = 0.0000001

    # Stamp Duty (for options): Rs. 15 per lakh of premium on buy side
    STAMP_DUTY_RATE = 0.000015  # 0.0015%? Wait no, stamp duty for options is Rs. 15 per lakh of premium (0.0015%) on buy side

    @classmethod
    def calculate_charges(cls, entry_price: float, exit_price: float, quantity: int) -> dict:
        """
        Calculate total charges for an options round-trip trade (buy + sell)
        :param entry_price: Premium at entry per unit
        :param exit_price: Premium at exit per unit
        :param quantity: Number of units (e.g., 50 for NIFTY lot)
        :returns: dict with all charges and total charges
        """
        # Calculate turnover on both sides
        buy_turnover = entry_price * quantity
        sell_turnover = exit_price * quantity
        total_turnover = buy_turnover + sell_turnover

        # Brokerage: Rs. 20 per order (buy + sell = Rs. 40 total)
        brokerage = cls.BROKERAGE_PER_ORDER * 2

        # STT: Only on sell side, 0.0625% of sell turnover
        stt = sell_turnover * cls.STT_RATE

        # NSE Transaction Charges: 0.005% on both sides
        txn_charges = total_turnover * cls.NSE_TXN_CHARGES

        # GST: 18% on (brokerage + txn charges)
        gst = (brokerage + txn_charges) * cls.GST_RATE

        # SEBI Fees: Rs. 10/crore = 0.00001% on total turnover
        sebi_fees = total_turnover * cls.SEBI_FEES

        # Stamp Duty: On buy side, Rs. 15/lakh of premium = 0.0015% of buy turnover
        stamp_duty = buy_turnover * cls.STAMP_DUTY_RATE

        # Total charges
        total_charges = brokerage + stt + txn_charges + gst + sebi_fees + stamp_duty

        logger.info(
            f"Charges calculated: entry={entry_price}, exit={exit_price}, qty={quantity} | "
            f"total=Rs.{total_charges:.2f} (brkr={brokerage}, stt={stt:.2f}, txn={txn_charges:.2f}, gst={gst:.2f}, sebi={sebi_fees:.4f}, stamp={stamp_duty:.4f})"
        )

        return {
            "brokerage": round(brokerage, 2),
            "stt": round(stt, 2),
            "transaction_charges": round(txn_charges, 2),
            "gst": round(gst, 2),
            "sebi_fees": round(sebi_fees, 4),
            "stamp_duty": round(stamp_duty, 4),
            "total_charges": round(total_charges, 2),
            "turnover": round(total_turnover, 2),
        }

    @classmethod
    def calculate_net_pnl(cls, entry_price: float, exit_price: float, quantity: int) -> dict:
        """
        Calculate net PnL after deducting all charges
        :returns: dict with gross_pnl, charges, net_pnl
        """
        gross_pnl = (exit_price - entry_price) * quantity
        charges = cls.calculate_charges(entry_price, exit_price, quantity)
        net_pnl = gross_pnl - charges["total_charges"]

        logger.info(
            f"PnL calculated: gross=Rs.{gross_pnl:.2f}, charges=Rs.{charges['total_charges']:.2f}, net=Rs.{net_pnl:.2f}"
        )

        return {
            "gross_pnl": round(gross_pnl, 2),
            "charges": charges,
            "net_pnl": round(net_pnl, 2),
        }
