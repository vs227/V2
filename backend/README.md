# AI Options Trader

NIFTY & BANKNIFTY Options Trading Assistant powered by Kotak Neo MCP.

## Architecture

```
app.py              → FastAPI entry point
config.py           → Environment-based settings
database.py         → SQLite trade journal
models.py           → Domain models (Pydantic)
schemas.py          → API request/response schemas
logger.py           → Centralized logging

services/
  kotak_service.py    → Kotak Neo SDK wrapper (neo_api_client)
  market_service.py   → Market data (NIFTY, BANKNIFTY, VIX)
  ai_service.py       → Rule-based market analyzer
  strategy_service.py → Deterministic strategy engine
  risk_service.py     → Risk management rules
  trade_service.py    → Trade execution & journaling

routes/
  market.py           → Market data & analysis endpoints
  trade.py            → Buy/sell/exit/modify endpoints
  portfolio.py        → Positions, holdings, limits
  analytics.py        → Win rate, PnL, daily stats
```

## Installation

### 1. Clone & Navigate

```bash
git clone <repo-url>
cd ai-options-trader
```

### 2. Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your Kotak Neo credentials:

```
KOTAK_CONSUMER_KEY=your_consumer_key
KOTAK_MOBILE_NUMBER=your_registered_mobile
KOTAK_UCC=your_unique_client_code
KOTAK_MPIN=your_mpin
MAX_DAILY_LOSS=5000
RISK_PERCENT=2.0
DEFAULT_QUANTITY=50
```

### 5. Get Kotak Neo API Credentials

1. Login to [Kotak Neo](https://kotakneo.com) app or website
2. Go to **Invest** tab → find **Trade API** card
3. Generate your **Consumer Key**
4. Register for **TOTP** at [kotaksecurities.com](https://www.kotaksecurities.com/platform/kotak-neo-trade-api/)
5. Set up TOTP on Google Authenticator
6. Note your **UCC** (Unique Client Code) from Profile section

### 6. Run the Server

```bash
python app.py
```

Server starts at `http://localhost:8000`

Swagger docs at `http://localhost:8000/docs`

## Authentication Flow

Kotak Neo uses TOTP-based 2FA:

```
1. NeoAPI(consumer_key) → Initialize client
2. totp_login(mobile, ucc, totp) → Get session
3. totp_validate(mpin) → Get trade token
4. Ready to trade
```

## API Reference

### Market Data

```bash
GET /market                         # Full overview
GET /market/nifty                   # NIFTY price
GET /market/banknifty               # BANKNIFTY price
GET /market/optionchain?symbol=NIFTY # Option chain
GET /market/vix                     # India VIX
GET /market/analysis?symbol=NIFTY   # AI analysis
```

### Trading

```bash
POST /trade/buy
{
  "symbol": "NIFTY",
  "strike": 24000,
  "expiry": "2025-01-30",
  "option_type": "CALL",
  "quantity": 50,
  "stoploss": 150,
  "target": 300
}

POST /trade/sell
{ "order_id": "order_123" }

POST /trade/exit
{ "trade_id": 1, "reason": "Target hit" }

POST /trade/modify-sl
{ "order_id": "order_123", "new_stoploss": 180 }

POST /trade/cancel
{ "order_id": "order_123" }
```

### Portfolio

```bash
GET /portfolio            # Full portfolio
GET /portfolio/positions  # Positions
GET /portfolio/holdings   # Holdings
GET /portfolio/limits     # Fund limits
```

### Orders & History

```bash
GET /trade/orders    # Current orders
GET /trade/positions # Current positions
GET /trade/history   # Trade journal
```

### Analytics

```bash
GET /analytics              # Overall stats
GET /analytics/daily?date=2025-01-15  # Daily breakdown
```

## Kotak Neo SDK Reference

| Function | Kotak SDK Method |
|----------|-----------------|
| Place Order | `client.place_order(exchange_segment="nse_fo", ...)` |
| Modify Order | `client.modify_order(order_id, ...)` |
| Cancel Order | `client.cancel_order(order_id)` |
| Order Book | `client.order_report()` |
| Trade Book | `client.trade_report()` |
| Positions | `client.positions()` |
| Holdings | `client.holdings()` |
| Limits | `client.limits(segment, exchange, product)` |
| Quotes | `client.quotes(instrument_tokens, quote_type)` |
| Search Scrip | `client.search_scrip(exchange_segment, symbol)` |

### Exchange Segments

| Segment | Value |
|---------|-------|
| NSE Cash | `nse_cm` |
| BSE Cash | `bse_cm` |
| NSE F&O | `nse_fo` |
| BSE F&O | `bse_fo` |
| MCX | `mcx_fo` |

### Order Types

| Type | Value |
|------|-------|
| Market | `MKT` |
| Limit | `L` |
| Stop Loss | `SL` |
| Stop Loss Market | `SL-M` |

### Products

| Product | Value |
|---------|-------|
| Intraday | `MIS` |
| Normal | `NRML` |
| CNC | `CNC` |

## Risk Rules

| Rule | Default |
|------|---------|
| Max open trades | 1 |
| Daily loss limit | ₹5,000 |
| Risk per trade | 2% |
| Min Risk:Reward | 1:2 |

## Future Improvements

- WebSocket live price streaming via Kotak Neo
- Trailing stoploss automation
- Multi-leg option strategies (spreads, straddles)
- Backtesting engine
- Dashboard UI
- Telegram/Discord notifications
- Historical data analysis
- Advanced OI-based signals
- Paper trading mode
