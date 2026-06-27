from models import AnalysisResult, StrategyRecommendation, SignalType, OptionType, TrendDirection
from config import get_settings
from logger import setup_logger

logger = setup_logger("strategy")


class StrategyService:

    def evaluate(
        self,
        analysis: AnalysisResult,
        symbol: str = "NIFTY",
        atm_details: dict = None
    ) -> StrategyRecommendation:
        logger.info(f"Evaluating strategy for {symbol}: trend={analysis.trend}, confidence={analysis.confidence}")
        settings = get_settings()

        if analysis.signal == SignalType.NO_TRADE or analysis.confidence < 50:
            return StrategyRecommendation(
                action=SignalType.NO_TRADE,
                symbol=symbol,
                strike=0,
                option_type=OptionType.CALL,
                entry_price=0,
                stoploss=0,
                target=0,
                quantity=settings.default_quantity,
                reason="Insufficient confidence or no clear signal",
                confidence=analysis.confidence,
            )

        entry = 200.0
        strike = 0.0
        option_type = OptionType.CALL if analysis.trend == TrendDirection.BULLISH else OptionType.PUT

        if atm_details:
            entry = atm_details.get("ltp", 200.0) or 200.0
            strike = atm_details.get("strike", 0.0)
            option_type = OptionType.CALL if atm_details.get("option_type") == "CE" else OptionType.PUT

        # Dynamic Stoploss (20% SL) and Target (40% Target) satisfying a 1:2 risk-reward ratio
        stoploss = entry * 0.80
        target = entry * 1.40

        action = SignalType.BUY_CALL if analysis.trend == TrendDirection.BULLISH else SignalType.BUY_PUT
        reason = f"{analysis.trend.value} setup: {analysis.reason}"
        if atm_details and atm_details.get("trading_symbol"):
            reason += f" | ATM Option: {atm_details['trading_symbol']}"

        recommendation = StrategyRecommendation(
            action=action,
            symbol=symbol,
            strike=strike,
            option_type=option_type,
            entry_price=round(entry, 2),
            stoploss=round(stoploss, 2),
            target=round(target, 2),
            quantity=settings.default_quantity,
            reason=reason,
            confidence=analysis.confidence,
        )
        logger.info(f"Recommendation: {recommendation.model_dump()}")
        return recommendation
