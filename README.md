#A modern AI-powered analyse and strike system, with a React frontend and FastAPI backend.

## Project Structure
- `backend/`: FastAPI backend with Groq-powered AI (Llama 3.1 70B), Supabase PostgreSQL, and Broker integration
- `frontend/`: React + Vite frontend (deployable on Vercel)

## Features
- AI-powered option chain analysis (Llama 3.1 via Groq)
- AutoTrade support with strict risk management
- Real-time portfolio tracking
- Trade journal with PnL including all charges
- Paper trading mode
- MCP server support for AI assistants

## Setup
### Backend
1. Copy `backend/.env.example` to `backend/.env` and fill in your credentials
2. Install dependencies: `pip install -r requirements.txt`
3. Run server: `python -m uvicorn app:app --reload`
4. Deploy on Render using `render.yaml`

### Frontend
1. Copy `frontend/.env.example` to `frontend/.env`
2. Install dependencies: `npm install`
3. Run dev server: `npm run dev`
4. Deploy on Vercel

## Supabase Setup
1. Create a Supabase project
2. Get the database URL from Settings > Database > Connection String
3. Run the backend once - it will create the `trades` table automatically!
# V2
