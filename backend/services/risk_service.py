from models import StrategyRecommendation, RiskDecision
from config import get_settings
from database import get_open_trades, get_daily_pnl
from logger import setup_logger
from datetime import datetime

logger = setup_logger("risk")


class RiskService:

    def evaluate(self, recommendation: StrategyRecommendation) -> RiskDecision:
        logger.info(f"Evaluating risk for: {recommendation.symbol} {recommendation.action}")
        settings = get_settings()

        open_trades = get_open_trades()
        if len(open_trades) >= settings.max_open_trades:
            return RiskDecision(
                approved=False,
                reason=f"Max open trades limit reached ({settings.max_open_trades})",
            )

        today = datetime.now().strftime("%Y-%m-%d")
        daily_pnl = get_daily_pnl(today)
        if daily_pnl <= -settings.max_daily_loss:
            return RiskDecision(
                approved=False,
                reason=f"Daily loss limit reached: ₹{abs(daily_pnl):.2f} / ₹{settings.max_daily_loss:.2f}",
            )

        if recommendation.entry_price <= 0:
            return RiskDecision(approved=False, reason="Invalid entry price")

        if recommendation.stoploss <= 0:
            return RiskDecision(approved=False, reason="Stoploss not set")

        if recommendation.target <= 0:
            return RiskDecision(approved=False, reason="Target not set")

        risk_per_unit = abs(recommendation.entry_price - recommendation.stoploss)
        reward_per_unit = abs(recommendation.target - recommendation.entry_price)

        if risk_per_unit == 0:
            return RiskDecision(approved=False, reason="Risk per unit is zero")

        risk_reward = reward_per_unit / risk_per_unit
        if risk_reward < settings.min_risk_reward:
            return RiskDecision(
                approved=False,
                reason=f"Risk:Reward {risk_reward:.2f} below minimum {settings.min_risk_reward}",
                risk_reward_ratio=round(risk_reward, 2),
            )

        risk_amount = risk_per_unit * recommendation.quantity
        max_risk = (settings.risk_percent / 100) * settings.max_daily_loss * 10
        if risk_amount > max_risk:
            return RiskDecision(
                approved=False,
                reason=f"Risk amount ₹{risk_amount:.2f} exceeds max ₹{max_risk:.2f}",
                risk_amount=risk_amount,
            )

        decision = RiskDecision(
            approved=True,
            reason="All risk checks passed",
            risk_amount=round(risk_amount, 2),
            risk_reward_ratio=round(risk_reward, 2),
        )
        logger.info(f"Risk approved: RR={risk_reward:.2f}, risk=₹{risk_amount:.2f}")
        return decision
