from fastapi import APIRouter, Query
from schemas import APIResponse
from services.kotak_service import get_kotak_service
from services.market_service import MarketService
from services.llm_ai_service import LLMService
from logger import setup_logger

logger = setup_logger("routes.market")
router = APIRouter(prefix="/market", tags=["Market"])

kotak = get_kotak_service()
market = MarketService(kotak)
ai = LLMService()


@router.get("", response_model=APIResponse)
async def get_market_overview():
    try:
        data = market.get_market_overview()
        return APIResponse(success=True, message="Market data fetched", data=data)
    except Exception as e:
        logger.error(f"Market overview failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.get("/nifty", response_model=APIResponse)
async def get_nifty():
    try:
        data = market.get_nifty_price()
        return APIResponse(success=True, message="NIFTY data fetched", data=data.model_dump(mode="json"))
    except Exception as e:
        logger.error(f"NIFTY fetch failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.get("/banknifty", response_model=APIResponse)
async def get_banknifty():
    try:
        data = market.get_banknifty_price()
        return APIResponse(success=True, message="BANKNIFTY data fetched", data=data.model_dump(mode="json"))
    except Exception as e:
        logger.error(f"BANKNIFTY fetch failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.get("/optionchain", response_model=APIResponse)
async def get_option_chain(symbol: str = Query("NIFTY", description="NIFTY or BANKNIFTY")):
    try:
        data = market.get_option_chain(symbol)
        return APIResponse(success=True, message=f"{symbol} option chain fetched", data=data)
    except Exception as e:
        logger.error(f"Option chain failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.get("/vix", response_model=APIResponse)
async def get_vix():
    try:
        data = market.get_india_vix()
        return APIResponse(success=True, message="India VIX fetched", data=data)
    except Exception as e:
        logger.error(f"VIX fetch failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.get("/analysis", response_model=APIResponse)
async def get_analysis(symbol: str = Query("NIFTY", description="NIFTY or BANKNIFTY")):
    try:
        nifty = market.get_nifty_ohlc()
        banknifty = market.get_banknifty_ohlc()
        option_chain = market.get_option_chain(symbol)
        vix = market.get_india_vix()

        result = ai.analyze_with_llm(nifty, banknifty, option_chain, vix)
        return APIResponse(success=True, message="Analysis complete", data=result.model_dump())
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return APIResponse(success=False, message=str(e))
