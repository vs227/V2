from fastapi import APIRouter
from schemas import APIResponse, BuyRequest, SellRequest, ExitRequest, ModifySLRequest, CancelRequest
from services.kotak_service import get_kotak_service
from services.trade_service import TradeService
from logger import setup_logger

logger = setup_logger("routes.trade")
router = APIRouter(prefix="/trade", tags=["Trade"])

kotak = get_kotak_service()
trade_service = TradeService(kotak)


@router.post("/buy", response_model=APIResponse)
async def buy(request: BuyRequest):
    try:
        logger.info(f"Buy request: {request.model_dump()}")
        result = trade_service.buy(request)
        return APIResponse(success=True, message="Buy order placed", data=result)
    except Exception as e:
        logger.error(f"Buy failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.post("/sell", response_model=APIResponse)
async def sell(request: SellRequest):
    try:
        logger.info(f"Sell request: {request.model_dump()}")
        result = trade_service.sell(request)
        return APIResponse(success=True, message="Sell order placed", data=result)
    except Exception as e:
        logger.error(f"Sell failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.post("/exit", response_model=APIResponse)
async def exit_trade(request: ExitRequest):
    try:
        logger.info(f"Exit request: trade_id={request.trade_id}")
        result = trade_service.exit_trade(request)
        return APIResponse(success=True, message="Trade exited", data=result)
    except Exception as e:
        logger.error(f"Exit failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.post("/modify-sl", response_model=APIResponse)
async def modify_sl(request: ModifySLRequest):
    try:
        result = trade_service.modify_stoploss(request.order_id, request.new_stoploss)
        return APIResponse(success=True, message="Stoploss modified", data=result)
    except Exception as e:
        logger.error(f"Modify SL failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.post("/cancel", response_model=APIResponse)
async def cancel(request: CancelRequest):
    try:
        result = trade_service.cancel_order(request.order_id)
        return APIResponse(success=True, message="Order cancelled", data=result)
    except Exception as e:
        logger.error(f"Cancel failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.get("/orders", response_model=APIResponse)
async def get_orders():
    try:
        data = trade_service.get_orders()
        return APIResponse(success=True, message="Orders fetched", data=data)
    except Exception as e:
        logger.error(f"Fetch orders failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.get("/positions", response_model=APIResponse)
async def get_positions():
    try:
        data = trade_service.get_positions()
        return APIResponse(success=True, message="Positions fetched", data=data)
    except Exception as e:
        logger.error(f"Fetch positions failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.get("/history", response_model=APIResponse)
async def get_history():
    try:
        data = trade_service.get_history()
        return APIResponse(success=True, message="Trade history fetched", data=data)
    except Exception as e:
        logger.error(f"Fetch history failed: {e}")
        return APIResponse(success=False, message=str(e))
