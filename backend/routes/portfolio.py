from fastapi import APIRouter
from schemas import APIResponse
from services.kotak_service import get_kotak_service
from logger import setup_logger

logger = setup_logger("routes.portfolio")
router = APIRouter(prefix="/portfolio", tags=["Portfolio"])

kotak = get_kotak_service()


@router.get("", response_model=APIResponse)
async def get_portfolio():
    if not kotak.is_authenticated:
        return APIResponse(success=False, message="Not authenticated with Kotak Neo")
    try:
        positions = kotak.get_positions()
        holdings = kotak.get_holdings()
        limits = kotak.get_limits()

        data = {
            "positions": positions,
            "holdings": holdings,
            "limits": limits,
        }
        return APIResponse(success=True, message="Portfolio fetched", data=data)
    except Exception as e:
        logger.error(f"Portfolio fetch failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.get("/positions", response_model=APIResponse)
async def get_positions():
    if not kotak.is_authenticated:
        return APIResponse(success=False, message="Not authenticated with Kotak Neo")
    try:
        data = kotak.get_positions()
        return APIResponse(success=True, message="Positions fetched", data=data)
    except Exception as e:
        logger.error(f"Positions fetch failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.get("/holdings", response_model=APIResponse)
async def get_holdings():
    if not kotak.is_authenticated:
        return APIResponse(success=False, message="Not authenticated with Kotak Neo")
    try:
        data = kotak.get_holdings()
        return APIResponse(success=True, message="Holdings fetched", data=data)
    except Exception as e:
        logger.error(f"Holdings fetch failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.get("/limits", response_model=APIResponse)
async def get_limits():
    if not kotak.is_authenticated:
        return APIResponse(success=False, message="Not authenticated with Kotak Neo")
    try:
        data = kotak.get_limits()
        return APIResponse(success=True, message="Limits fetched", data=data)
    except Exception as e:
        logger.error(f"Limits fetch failed: {e}")
        return APIResponse(success=False, message=str(e))
