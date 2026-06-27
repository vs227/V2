from datetime import datetime
from config import get_settings
from logger import setup_logger
import httpx
import psycopg2
from psycopg2.extras import DictCursor
import socket
from urllib.parse import urlparse, unquote
from psycopg2.pool import ThreadedConnectionPool

logger = setup_logger("database")
settings = get_settings()

# Initialize httpx client for Supabase REST API
supabase_client = None
if settings.supabase_url and settings.supabase_key:
    supabase_client = httpx.Client(
        base_url=f"{settings.supabase_url}/rest/v1",
        headers={
            "apikey": settings.supabase_key,
            "Authorization": f"Bearer {settings.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        },
        timeout=10.0
    )
    logger.info("Supabase HTTP client initialized successfully")

# connection pool
_pool = None

def get_connection_params():
    """Parse Supabase DB URL into connection params with IPv4 hostaddr"""
    url = urlparse(settings.supabase_db_url)
    params = {
        'dbname': url.path[1:] if url.path else 'postgres',
        'user': unquote(url.username) if url.username else 'postgres',
        'password': unquote(url.password) if url.password else '',
        'host': url.hostname,
        'port': url.port or 5432,
        'connect_timeout': 10
    }
    
    try:
        addrs = socket.getaddrinfo(params['host'], None, socket.AF_INET)
        if addrs:
            ipv4 = addrs[0][4][0]
            params['hostaddr'] = ipv4
            logger.info(f"Resolved {params['host']} to IPv4: {ipv4}")
    except Exception as e:
        logger.warning(f"Could not resolve {params['host']} to IPv4: {e}")
        
    return params

class ConnectionProxy:
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
        self._returned = False

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        if not self._returned:
            try:
                self._pool.putconn(self._conn)
            except Exception as e:
                logger.error(f"Error returning connection to pool: {e}")
            finally:
                self._returned = True

    def __del__(self):
        if not self._returned:
            self.close()

def get_db_connection():
    global _pool
    params = get_connection_params()
        
    if _pool is None:
        try:
            logger.info("Initializing database connection pool...")
            _pool = ThreadedConnectionPool(2, 20, **params)
            logger.info("Database connection pool initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database connection pool: {e}")
            
    try:
        if _pool:
            conn = _pool.getconn()
            return ConnectionProxy(conn, _pool)
        else:
            return psycopg2.connect(**params)
    except Exception as e:
        logger.warning(f"Failed to get database connection: {e}")
        raise

def init_db() -> None:
    logger.info("Database ready")

def insert_trade(trade: dict) -> int:
    try:
        # Default all optional fields to prevent None errors
        default_fields = [
            "gross_pnl", "total_charges", "brokerage", "stt",
            "transaction_charges", "gst", "sebi_fees", "stamp_duty",
            "exit_price", "strike", "expiry", "option_type", "stoploss", "target", "order_id", "strategy", "reason"
        ]
        for field in default_fields:
            if field not in trade:
                trade[field] = None if field in ["strike", "expiry", "option_type", "stoploss", "target", "order_id", "strategy", "reason"] else 0.0

        if supabase_client:
            response = supabase_client.post("/trades", json=trade)
            response.raise_for_status()
            result = response.json()
            trade_id = result[0]["id"]
            logger.info(f"Trade inserted (Supabase REST): id={trade_id}, symbol={trade.get('symbol')}")
            return trade_id
        else:
            conn = get_db_connection()
            cursor = None
            try:
                cursor = conn.cursor()
                sql = """
                    INSERT INTO trades (
                        timestamp, symbol, strike, expiry, option_type,
                        entry_price, exit_price, quantity, stoploss, target, pnl,
                        gross_pnl, total_charges, brokerage, stt, transaction_charges,
                        gst, sebi_fees, stamp_duty, strategy, reason, status, order_id
                    ) VALUES (
                        %(timestamp)s, %(symbol)s, %(strike)s, %(expiry)s, %(option_type)s,
                        %(entry_price)s, %(exit_price)s, %(quantity)s, %(stoploss)s, %(target)s, %(pnl)s,
                        %(gross_pnl)s, %(total_charges)s, %(brokerage)s, %(stt)s, %(transaction_charges)s,
                        %(gst)s, %(sebi_fees)s, %(stamp_duty)s, %(strategy)s, %(reason)s, %(status)s, %(order_id)s
                    ) RETURNING id
                """
                cursor.execute(sql, trade)
                trade_id = cursor.fetchone()[0]
                conn.commit()
                logger.info(f"Trade inserted (psycopg2): id={trade_id}, symbol={trade.get('symbol')}")
                return trade_id
            finally:
                if cursor:
                    cursor.close()
                conn.close()
    except Exception as e:
        logger.error(f"Failed to insert trade: {e}")
        raise

def get_trade(trade_id: int) -> dict:
    try:
        if supabase_client:
            response = supabase_client.get("/trades", params={"id": f"eq.{trade_id}", "select": "*"})
            response.raise_for_status()
            result = response.json()
            return result[0] if result else None
        else:
            conn = get_db_connection()
            cursor = None
            try:
                cursor = conn.cursor(cursor_factory=DictCursor)
                cursor.execute("SELECT * FROM trades WHERE id = %s", (trade_id,))
                trade = cursor.fetchone()
                return dict(trade) if trade else None
            finally:
                if cursor:
                    cursor.close()
                conn.close()
    except Exception as e:
        logger.error(f"Failed to get trade {trade_id}: {e}")
        return None

def get_open_trades(symbol: str = None) -> list:
    try:
        if supabase_client:
            params = {"status": "eq.OPEN", "order": "timestamp.desc", "select": "*"}
            if symbol:
                params["symbol"] = f"eq.{symbol}"
            response = supabase_client.get("/trades", params=params)
            response.raise_for_status()
            return response.json()
        else:
            conn = get_db_connection()
            cursor = None
            try:
                cursor = conn.cursor(cursor_factory=DictCursor)
                if symbol:
                    cursor.execute("SELECT * FROM trades WHERE status = 'OPEN' AND symbol = %s ORDER BY timestamp DESC", (symbol,))
                else:
                    cursor.execute("SELECT * FROM trades WHERE status = 'OPEN' ORDER BY timestamp DESC")
                trades = cursor.fetchall()
                return [dict(t) for t in trades]
            finally:
                if cursor:
                    cursor.close()
                conn.close()
    except Exception as e:
        logger.error(f"Failed to get open trades: {e}")
        return []

def get_all_trades(limit: int = 100, symbol: str = None) -> list:
    try:
        if supabase_client:
            params = {"order": "timestamp.desc", "limit": str(limit), "select": "*"}
            if symbol:
                params["symbol"] = f"eq.{symbol}"
            response = supabase_client.get("/trades", params=params)
            response.raise_for_status()
            return response.json()
        else:
            conn = get_db_connection()
            cursor = None
            try:
                cursor = conn.cursor(cursor_factory=DictCursor)
                if symbol:
                    cursor.execute("SELECT * FROM trades WHERE symbol = %s ORDER BY timestamp DESC LIMIT %s", (symbol, limit))
                else:
                    cursor.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT %s", (limit,))
                trades = cursor.fetchall()
                return [dict(t) for t in trades]
            finally:
                if cursor:
                    cursor.close()
                conn.close()
    except Exception as e:
        logger.error(f"Failed to get all trades: {e}")
        return []

def get_closed_trades(limit: int = 100, symbol: str = None) -> list:
    try:
        if supabase_client:
            params = {"status": "eq.CLOSED", "order": "timestamp.desc", "limit": str(limit), "select": "*"}
            if symbol:
                params["symbol"] = f"eq.{symbol}"
            response = supabase_client.get("/trades", params=params)
            response.raise_for_status()
            return response.json()
        else:
            conn = get_db_connection()
            cursor = None
            try:
                cursor = conn.cursor(cursor_factory=DictCursor)
                if symbol:
                    cursor.execute("SELECT * FROM trades WHERE status = 'CLOSED' AND symbol = %s ORDER BY timestamp DESC LIMIT %s", (symbol, limit))
                else:
                    cursor.execute("SELECT * FROM trades WHERE status = 'CLOSED' ORDER BY timestamp DESC LIMIT %s", (limit,))
                trades = cursor.fetchall()
                return [dict(t) for t in trades]
            finally:
                if cursor:
                    cursor.close()
                conn.close()
    except Exception as e:
        logger.error(f"Failed to get closed trades: {e}")
        return []

def update_trade(trade_id: int, updates: dict) -> bool:
    try:
        if supabase_client:
            updates["updated_at"] = datetime.now().isoformat()
            response = supabase_client.patch(f"/trades?id=eq.{trade_id}", json=updates)
            response.raise_for_status()
            result = response.json()
            return len(result) > 0
        else:
            conn = get_db_connection()
            cursor = None
            try:
                cursor = conn.cursor()
                set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
                values = list(updates.values())
                values.append(datetime.now())
                values.append(trade_id)
                sql = f"UPDATE trades SET {set_clause}, updated_at = %s WHERE id = %s"
                cursor.execute(sql, values)
                conn.commit()
                return cursor.rowcount > 0
            finally:
                if cursor:
                    cursor.close()
                conn.close()
    except Exception as e:
        logger.error(f"Failed to update trade {trade_id}: {e}")
        return False

def get_daily_pnl(date_str: str = None) -> float:
    try:
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        if supabase_client:
            response = supabase_client.get(
                "/trades",
                params={
                    "status": "eq.CLOSED",
                    "timestamp": [f"gte.{date_str}T00:00:00", f"lte.{date_str}T23:59:59"],
                    "select": "pnl"
                }
            )
            response.raise_for_status()
            trades = response.json()
            return float(sum(t["pnl"] or 0 for t in trades))
        else:
            conn = get_db_connection()
            cursor = None
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE DATE(timestamp) = %s AND status = 'CLOSED'",
                    (date_str,)
                )
                return float(cursor.fetchone()[0])
            finally:
                if cursor:
                    cursor.close()
                conn.close()
    except Exception as e:
        logger.error(f"Failed to get daily P&L: {e}")
        return 0.0
