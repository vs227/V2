from fastapi import APIRouter, Query
from schemas import APIResponse
from database import get_all_trades, get_trades_by_date, get_daily_pnl
from logger import setup_logger
from datetime import datetime

logger = setup_logger("routes.analytics")
router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("", response_model=APIResponse)
async def get_analytics():
    try:
        trades = get_all_trades(limit=500)
        today = datetime.now().strftime("%Y-%m-%d")
        today_pnl = get_daily_pnl(today)

        total_trades = len(trades)
        closed = [t for t in trades if t["status"] == "CLOSED"]
        winners = [t for t in closed if t["pnl"] > 0]
        losers = [t for t in closed if t["pnl"] < 0]

        total_pnl = sum(t["pnl"] for t in closed)
        total_gross_pnl = sum(t.get("gross_pnl", 0) for t in closed)
        total_charges = sum(t.get("total_charges", 0) for t in closed)
        win_rate = (len(winners) / len(closed) * 100) if closed else 0
        avg_win = (sum(t["pnl"] for t in winners) / len(winners)) if winners else 0
        avg_loss = (sum(t["pnl"] for t in losers) / len(losers)) if losers else 0

        data = {
            "total_trades": total_trades,
            "closed_trades": len(closed),
            "open_trades": total_trades - len(closed),
            "winners": len(winners),
            "losers": len(losers),
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "total_gross_pnl": round(total_gross_pnl, 2),
            "total_charges": round(total_charges, 2),
            "today_pnl": round(today_pnl, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0,
        }
        return APIResponse(success=True, message="Analytics computed", data=data)
    except Exception as e:
        logger.error(f"Analytics failed: {e}")
        return APIResponse(success=False, message=str(e))


@router.get("/daily", response_model=APIResponse)
async def get_daily_trades(date: str = Query(None, description="Date YYYY-MM-DD")):
    try:
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        trades = get_trades_by_date(target_date)
        pnl = get_daily_pnl(target_date)

        data = {
            "date": target_date,
            "trades": trades,
            "trade_count": len(trades),
            "daily_pnl": round(pnl, 2),
        }
        return APIResponse(success=True, message=f"Daily analytics for {target_date}", data=data)
    except Exception as e:
        logger.error(f"Daily analytics failed: {e}")
        return APIResponse(success=False, message=str(e))
