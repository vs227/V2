from models import AnalysisResult, TrendDirection, SignalType, MarketData
from logger import setup_logger

logger = setup_logger("ai")


class AIService:

    def analyze(
        self,
        nifty: MarketData,
        banknifty: MarketData,
        option_chain: dict,
        vix: dict,
    ) -> AnalysisResult:
        logger.info("Running market analysis")

        trend = self._detect_trend(nifty)
        volume_signal = self._analyze_volume(nifty)
        oi_signal = self._analyze_oi(option_chain)
        sentiment = self._market_sentiment(vix)

        confidence = self._calculate_confidence(trend, volume_signal, oi_signal, sentiment)
        signal = self._determine_signal(trend, confidence)
        reason = self._build_reason(trend, volume_signal, oi_signal, sentiment)

        result = AnalysisResult(
            trend=trend,
            confidence=round(confidence, 2),
            signal=signal,
            reason=reason,
        )
        logger.info(f"Analysis complete: {result.model_dump()}")
        return result

    def _detect_trend(self, data: MarketData) -> TrendDirection:
        if data.ltp <= 0 or data.close <= 0:
            return TrendDirection.SIDEWAYS

        change_pct = ((data.ltp - data.close) / data.close) * 100

        if change_pct > 0.3:
            return TrendDirection.BULLISH
        elif change_pct < -0.3:
            return TrendDirection.BEARISH
        return TrendDirection.SIDEWAYS

    def _analyze_volume(self, data: MarketData) -> str:
        if data.volume <= 0:
            return "NO_DATA"

        if data.ltp > data.close and data.volume > 0:
            return "INCREASING"
        elif data.ltp < data.close and data.volume > 0:
            return "DECREASING"
        return "NEUTRAL"

    def _analyze_oi(self, option_chain: dict) -> str:
        data = option_chain.get("data", [])
        if not data:
            return "NEUTRAL"

        total_call_oi = sum(item.get("call_oi", 0) for item in data if isinstance(item, dict))
        total_put_oi = sum(item.get("put_oi", 0) for item in data if isinstance(item, dict))

        if total_put_oi > total_call_oi * 1.2:
            return "BULLISH"
        elif total_call_oi > total_put_oi * 1.2:
            return "BEARISH"
        return "NEUTRAL"

    def _market_sentiment(self, vix: dict) -> str:
        vix_value = vix.get("vix")
        if vix_value is None:
            return "NEUTRAL"

        if vix_value > 20:
            return "FEARFUL"
        elif vix_value < 13:
            return "GREEDY"
        return "NEUTRAL"

    def _calculate_confidence(
        self, trend: TrendDirection, volume: str, oi: str, sentiment: str
    ) -> float:
        score = 0.0

        if trend != TrendDirection.SIDEWAYS:
            score += 30

        if volume == "INCREASING" and trend == TrendDirection.BULLISH:
            score += 25
        elif volume == "DECREASING" and trend == TrendDirection.BEARISH:
            score += 25
        elif volume != "NO_DATA":
            score += 10

        if oi == "BULLISH" and trend == TrendDirection.BULLISH:
            score += 25
        elif oi == "BEARISH" and trend == TrendDirection.BEARISH:
            score += 25
        elif oi != "NEUTRAL":
            score += 5

        if sentiment == "FEARFUL" and trend == TrendDirection.BEARISH:
            score += 20
        elif sentiment == "GREEDY" and trend == TrendDirection.BULLISH:
            score += 20
        elif sentiment == "NEUTRAL":
            score += 10

        return min(score, 100.0)

    def _determine_signal(self, trend: TrendDirection, confidence: float) -> SignalType:
        if confidence < 50:
            return SignalType.NO_TRADE

        if trend == TrendDirection.BULLISH:
            return SignalType.BUY_CALL
        elif trend == TrendDirection.BEARISH:
            return SignalType.BUY_PUT
        return SignalType.NO_TRADE

    def _build_reason(self, trend: TrendDirection, volume: str, oi: str, sentiment: str) -> str:
        parts = [
            f"Trend: {trend.value}",
            f"Volume: {volume}",
            f"OI Signal: {oi}",
            f"Sentiment: {sentiment}",
        ]
        return " | ".join(parts)
