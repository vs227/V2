from groq import Groq
from config import get_settings
from models import AnalysisResult, TrendDirection, SignalType
from logger import setup_logger

logger = setup_logger("llm_ai")

settings = get_settings()


class LLMService:
    def __init__(self):
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is required! Please set it in your .env file.")
        self.client = Groq(api_key=settings.groq_api_key)
        logger.info("LLM Service initialized with Groq API")

    def analyze_with_llm(
        self,
        nifty_data: dict,
        banknifty_data: dict,
        option_chain: dict,
        vix: dict
    ) -> AnalysisResult:
        try:
            prompt = self._build_analysis_prompt(
                nifty_data, banknifty_data, option_chain, vix
            )

            chat_completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert options trader and market analyst specialized in NIFTY and BANKNIFTY scalping.
Analyze the market data and respond ONLY in valid JSON format with the following structure:
{
    "trend": "BULLISH" | "BEARISH" | "SIDEWAYS",
    "signal": "BUY_CALL" | "BUY_PUT" | "NO_TRADE",
    "confidence": 0-100,
    "reasoning": "brief, clear explanation of your decision"
}

Important rules:
- Only respond with valid JSON (no other text)
- Only give BUY_CALL or BUY_PUT if confidence is >= 60
- Be conservative and don't overtrade
- Focus on scalping opportunities (short-term trades)
"""
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.1,
                max_tokens=300
            )

            response_text = chat_completion.choices[0].message.content.strip()

            # Parse JSON response
            import json
            import re
            json_match = re.search(r'\{[^{}]*\}', response_text)
            if json_match:
                response_json = json.loads(json_match.group())
            else:
                raise ValueError(f"LLM did not return valid JSON: {response_text}")

            # Map to enums
            trend_map = {
                "BULLISH": TrendDirection.BULLISH,
                "BEARISH": TrendDirection.BEARISH,
                "SIDEWAYS": TrendDirection.SIDEWAYS
            }
            signal_map = {
                "BUY_CALL": SignalType.BUY_CALL,
                "BUY_PUT": SignalType.BUY_PUT,
                "NO_TRADE": SignalType.NO_TRADE
            }

            result = AnalysisResult(
                trend=trend_map.get(response_json.get("trend", "SIDEWAYS"), TrendDirection.SIDEWAYS),
                confidence=min(max(0, response_json.get("confidence", 0)), 100),
                signal=signal_map.get(response_json.get("signal", "NO_TRADE"), SignalType.NO_TRADE),
                reason=response_json.get("reasoning", "LLM analysis")
            )

            logger.info(f"LLM Analysis complete: {result.model_dump()}")
            return result

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            raise RuntimeError(f"LLM analysis failed: {e}") from e

    def _prune_option_chain(self, option_chain: dict, spot_price: float) -> str:
        if not option_chain or not isinstance(option_chain, dict):
            return "No option chain data available."
            
        data_list = option_chain.get("data", [])
        if not isinstance(data_list, list) or not data_list:
            # Fallback in case raw contracts list is passed
            contracts = option_chain.get("scrip", [])
            if not isinstance(contracts, list) or not contracts:
                return "No contracts found in option chain."
            
            # Format raw contracts fallback
            lines = []
            for c in contracts[:10]:
                ts = c.get("tradingSymbol", c.get("pTrdSym", ""))
                strike = c.get("strike")
                opt_type = c.get("option_type")
                lines.append(f"- {ts} | Strike: {strike} | Type: {opt_type}")
            return "\n".join(lines)
            
        # Format the grouped option chain list
        lines = []
        for strike_item in data_list:
            strike = strike_item.get("strike")
            ce = strike_item.get("CE")
            pe = strike_item.get("PE")
            
            ce_str = f"CE LTP: {ce['ltp']} (Vol: {ce['volume']}, OI: {ce['oi']})" if ce else "CE: N/A"
            pe_str = f"PE LTP: {pe['ltp']} (Vol: {pe['volume']}, OI: {pe['oi']})" if pe else "PE: N/A"
            
            lines.append(f"Strike {strike}: {ce_str} | {pe_str}")
            
        return "\n".join(lines)

    def _build_analysis_prompt(self, nifty, banknifty, option_chain, vix):
        # Determine spot price to use for pruning
        contracts = []
        if isinstance(option_chain, dict):
            contracts = option_chain.get("data", option_chain.get("scrip", []))
            
        first_symbol = ""
        if isinstance(contracts, list) and contracts:
            first_symbol = contracts[0].get("tradingSymbol", contracts[0].get("pTrdSym", ""))
            
        spot_price = nifty.ltp
        if "BANKNIFTY" in first_symbol:
            spot_price = banknifty.ltp
            
        pruned_chain = self._prune_option_chain(option_chain, spot_price)
        
        return f"""
NIFTY 50 Data:
- Last Traded Price (LTP): {nifty.ltp}
- Open: {nifty.open}
- High: {nifty.high}
- Low: {nifty.low}
- Previous Close: {nifty.close}
- Volume: {nifty.volume}

BANKNIFTY Data:
- Last Traded Price (LTP): {banknifty.ltp}
- Open: {banknifty.open}
- High: {banknifty.high}
- Low: {banknifty.low}
- Previous Close: {banknifty.close}

Option Chain Summary (Nearest ATM strikes):
{pruned_chain}

India VIX:
{vix}

Analyze this data for a short-term scalping opportunity.
"""
