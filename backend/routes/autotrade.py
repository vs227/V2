from fastapi import APIRouter
from schemas import APIResponse
from services.autotrade_service import get_autotrade_service
from logger import setup_logger

router = APIRouter(prefix="/autotrade", tags=["AutoTrade"])
logger = setup_logger("autotrade")


@router.post("/enable", response_model=APIResponse)
async def enable_autotrade():
    try:
        autotrade = get_autotrade_service()
        autotrade.enable()
        return APIResponse(
            success=True,
            message="AutoTrade enabled",
            data={"enabled": True}
        )
    except Exception as e:
        logger.error(f"Enable autotrade failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.post("/disable", response_model=APIResponse)
async def disable_autotrade():
    try:
        autotrade = get_autotrade_service()
        autotrade.disable()
        return APIResponse(
            success=True,
            message="AutoTrade disabled",
            data={"enabled": False}
        )
    except Exception as e:
        logger.error(f"Disable autotrade failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.get("/status", response_model=APIResponse)
async def get_autotrade_status():
    try:
        autotrade = get_autotrade_service()
        from datetime import datetime
        rate_limited = False
        cooldown_remaining = 0
        if autotrade._rate_limited_until and datetime.now() < autotrade._rate_limited_until:
            rate_limited = True
            cooldown_remaining = int((autotrade._rate_limited_until - datetime.now()).total_seconds())
        return APIResponse(
            success=True,
            message="AutoTrade status fetched",
            data={
                "enabled": autotrade.is_enabled,
                "rate_limited": rate_limited,
                "cooldown_remaining": cooldown_remaining
            }
        )
    except Exception as e:
        logger.error(f"Get autotrade status failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.get("/settings", response_model=APIResponse)
async def get_settings_endpoint():
    try:
        from config import get_settings
        settings = get_settings()
        return APIResponse(
            success=True,
            message="Settings fetched",
            data={
                "max_daily_loss": settings.max_daily_loss,
                "risk_percent": settings.risk_percent,
                "default_quantity": settings.default_quantity,
                "min_risk_reward": settings.min_risk_reward,
                "max_open_trades": settings.max_open_trades,
                "paper_trading": settings.paper_trading,
            }
        )
    except Exception as e:
        logger.error(f"Get settings failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.post("/settings", response_model=APIResponse)
async def update_settings_endpoint(payload: dict):
    try:
        from config import get_settings
        settings = get_settings()
        
        # Update settings dynamically in memory
        if "max_daily_loss" in payload:
            settings.max_daily_loss = float(payload["max_daily_loss"])
        if "risk_percent" in payload:
            settings.risk_percent = float(payload["risk_percent"])
        if "default_quantity" in payload:
            settings.default_quantity = int(payload["default_quantity"])
        if "min_risk_reward" in payload:
            settings.min_risk_reward = float(payload["min_risk_reward"])
        if "max_open_trades" in payload:
            settings.max_open_trades = int(payload["max_open_trades"])
        if "paper_trading" in payload:
            settings.paper_trading = bool(payload["paper_trading"])
            
        logger.info(f"Settings updated: {settings.__dict__}")
        return APIResponse(
            success=True,
            message="Settings updated successfully",
            data={
                "max_daily_loss": settings.max_daily_loss,
                "risk_percent": settings.risk_percent,
                "default_quantity": settings.default_quantity,
                "min_risk_reward": settings.min_risk_reward,
                "max_open_trades": settings.max_open_trades,
                "paper_trading": settings.paper_trading,
            }
        )
    except Exception as e:
        logger.error(f"Update settings failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.get("/last-decision", response_model=APIResponse)
async def get_last_decision():
    try:
        autotrade = get_autotrade_service()
        return APIResponse(
            success=True,
            message="Last decision fetched",
            data=autotrade.last_analysis
        )
    except Exception as e:
        logger.error(f"Get last decision failed: {e}")
        return APIResponse(success=False, message=str(e))
