import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import init_db
from logger import setup_logger
from routes import market, trade, portfolio, analytics, chat, autotrade
from services.kotak_service import get_kotak_service
from schemas import LoginRequest, APIResponse
import time

logger = setup_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Options Trader")
    init_db()
    logger.info("Database ready")
    yield
    logger.info("Shutting down AI Options Trader")


app = FastAPI(
    title="AI Options Trader",
    description="NIFTY & BANKNIFTY Options Trading Assistant powered by Kotak Neo MCP",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    logger.info(f"-> {request.method} {request.url.path}")
    response = await call_next(request)
    duration = round((time.time() - start) * 1000, 2)
    logger.info(f"<- {request.method} {request.url.path} [{response.status_code}] {duration}ms")
    return response


app.include_router(market.router)
app.include_router(trade.router)
app.include_router(portfolio.router)
app.include_router(analytics.router)
app.include_router(chat.router)
app.include_router(autotrade.router)


@app.post("/login", response_model=APIResponse, tags=["Authentication"])
async def login(request: LoginRequest):
    try:
        kotak = get_kotak_service()
        res = kotak.login(totp=request.totp)
        return APIResponse(success=True, message="Authenticated with Kotak Neo", data=res)
    except Exception as e:
        logger.error(f"Login endpoint failed: {e}")
        return APIResponse(success=False, message=str(e))


from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse


app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")


@app.get("/favicon.svg", tags=["Health"])
async def favicon():
    return FileResponse("static/favicon.svg")


@app.get("/", tags=["Health"])
async def root():
    return FileResponse("static/index.html")


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False, ws="none")
