from datetime import datetime
from config import get_settings
from logger import setup_logger
from supabase import create_client, Client
import psycopg2
from psycopg2.extras import DictCursor
import socket
from urllib.parse import urlparse, unquote
from psycopg2.pool import ThreadedConnectionPool

logger = setup_logger("database")
settings = get_settings()

# Initialize Supabase client
supabase: Client = None
try:
    if settings.supabase_url and settings.supabase_key:
        supabase = create_client(settings.supabase_url, settings.supabase_key)
        logger.info("Supabase client initialized successfully")
except Exception as e:
    logger.warning(f"Failed to initialize Supabase client: {e}")

# Fallback to psycopg2 if needed
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
    
    # Try to resolve hostname to IPv4 and add hostaddr
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
            # Fallback to direct connection if pool isn't available
            return psycopg2.connect(**params)
    except Exception as e:
        logger.warning(f"Failed to get database connection: {e}")
        raise  # Re-raise so individual DB operations can handle it

def init_db() -> None:
    try:
        # Try using Supabase client first to create table via RPC or just let it fail silently
        # The table should already exist in Supabase
        logger.info("Database initialization skipped (table should exist in Supabase)")
    except Exception as e:
        logger.error(f"Database initialization failed (will retry later): {e}")

def insert_trade(trade: dict) -> int:
    try:
        if supabase:
            # Use Supabase client
            default_fields = [
                "gross_pnl", "total_charges", "brokerage", "stt",
                "transaction_charges", "gst", "sebi_fees", "stamp_duty",
                "exit_price", "strike", "expiry", "option_type", "stoploss", "target", "order_id", "strategy", "reason"
            ]
            for field in default_fields:
                if field not in trade:
                    trade[field] = None if field in ["strike", "expiry", "option_type", "stoploss", "target", "order_id", "strategy", "reason"] else 0.0
            
            response = supabase.table("trades").insert(trade).execute()
            trade_id = response.data[0]["id"]
            logger.info(f"Trade inserted (Supabase): id={trade_id}, symbol={trade.get('symbol')}")
            return trade_id
        else:
            # Fallback to psycopg2
            conn = get_db_connection()
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
            
            default_fields = [
                "gross_pnl", "total_charges", "brokerage", "stt",
                "transaction_charges", "gst", "sebi_fees", "stamp_duty",
                "exit_price", "strike", "expiry", "option_type", "stoploss", "target", "order_id", "strategy", "reason"
            ]
            for field in default_fields:
                if field not in trade:
                    trade[field] = None if field in ["strike", "expiry", "option_type", "stoploss", "target", "order_id", "strategy", "reason"] else 0.0
                    
            cursor.execute(sql, trade)
            trade_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()
            logger.info(f"Trade inserted (psycopg2): id={trade_id}, symbol={trade.get('symbol')}")
            return trade_id
    except Exception as e:
        logger.error(f"Failed to insert trade: {e}")
        raise

def get_trade(trade_id: int) -> dict:
    try:
        if supabase:
            response = supabase.table("trades").select("*").eq("id", trade_id).single().execute()
            return response.data
        else:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=DictCursor)
            cursor.execute("SELECT * FROM trades WHERE id = %s", (trade_id,))
            trade = cursor.fetchone()
            cursor.close()
            conn.close()
            return dict(trade) if trade else None
    except Exception as e:
        logger.error(f"Failed to get trade {trade_id}: {e}")
        return None

def get_open_trades(symbol: str = None) -> list:
    try:
        if supabase:
            query = supabase.table("trades").select("*").eq("status", "OPEN").order("timestamp", desc=True)
            if symbol:
                query = query.eq("symbol", symbol)
            response = query.execute()
            return response.data
        else:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=DictCursor)
            if symbol:
                cursor.execute("SELECT * FROM trades WHERE status = 'OPEN' AND symbol = %s ORDER BY timestamp DESC", (symbol,))
            else:
                cursor.execute("SELECT * FROM trades WHERE status = 'OPEN' ORDER BY timestamp DESC")
            trades = cursor.fetchall()
            cursor.close()
            conn.close()
            return [dict(t) for t in trades]
    except Exception as e:
        logger.error(f"Failed to get open trades: {e}")
        return []

def get_all_trades(limit: int = 100, symbol: str = None) -> list:
    try:
        if supabase:
            query = supabase.table("trades").select("*").order("timestamp", desc=True).limit(limit)
            if symbol:
                query = query.eq("symbol", symbol)
            response = query.execute()
            return response.data
        else:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=DictCursor)
            if symbol:
                cursor.execute("SELECT * FROM trades WHERE symbol = %s ORDER BY timestamp DESC LIMIT %s", (symbol, limit))
            else:
                cursor.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT %s", (limit,))
            trades = cursor.fetchall()
            cursor.close()
            conn.close()
            return [dict(t) for t in trades]
    except Exception as e:
        logger.error(f"Failed to get all trades: {e}")
        return []

def get_closed_trades(limit: int = 100, symbol: str = None) -> list:
    try:
        if supabase:
            query = supabase.table("trades").select("*").eq("status", "CLOSED").order("timestamp", desc=True).limit(limit)
            if symbol:
                query = query.eq("symbol", symbol)
            response = query.execute()
            return response.data
        else:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=DictCursor)
            if symbol:
                cursor.execute("SELECT * FROM trades WHERE status = 'CLOSED' AND symbol = %s ORDER BY timestamp DESC LIMIT %s", (symbol, limit))
            else:
                cursor.execute("SELECT * FROM trades WHERE status = 'CLOSED' ORDER BY timestamp DESC LIMIT %s", (limit,))
            trades = cursor.fetchall()
            cursor.close()
            conn.close()
            return [dict(t) for t in trades]
    except Exception as e:
        logger.error(f"Failed to get closed trades: {e}")
        return []

def get_trades_by_date(date_str: str) -> list:
    try:
        if supabase:
            # Use Supabase filter for date
            response = supabase.table("trades").select("*").filter("timestamp", "gte", f"{date_str}T00:00:00").filter("timestamp", "lte", f"{date_str}T23:59:59").order("timestamp", desc=True).execute()
            return response.data
        else:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=DictCursor)
            cursor.execute(
                "SELECT * FROM trades WHERE DATE(timestamp) = %s ORDER BY timestamp DESC",
                (date_str,)
            )
            trades = cursor.fetchall()
            cursor.close()
            conn.close()
            return [dict(t) for t in trades]
    except Exception as e:
        logger.error(f"Failed to get trades for date {date_str}: {e}")
        return []

def update_trade(trade_id: int, updates: dict) -> bool:
    try:
        if supabase:
            updates["updated_at"] = datetime.now().isoformat()
            response = supabase.table("trades").update(updates).eq("id", trade_id).execute()
            return len(response.data) > 0
        else:
            conn = get_db_connection()
            cursor = conn.cursor()
            set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
            values = list(updates.values())
            values.append(trade_id)
            values.append(datetime.now())
            sql = f"UPDATE trades SET {set_clause}, updated_at = %s WHERE id = %s"
            cursor.execute(sql, values)
            conn.commit()
            updated = cursor.rowcount > 0
            cursor.close()
            conn.close()
            return updated
    except Exception as e:
        logger.error(f"Failed to update trade {trade_id}: {e}")
        return False

def get_daily_pnl(date_str: str = None) -> float:
    try:
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        if supabase:
            # Get all closed trades for the day and sum pnl
            response = supabase.table("trades").select("pnl").eq("status", "CLOSED").filter("timestamp", "gte", f"{date_str}T00:00:00").filter("timestamp", "lte", f"{date_str}T23:59:59").execute()
            total = sum(t["pnl"] or 0 for t in response.data)
            return float(total)
        else:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE DATE(timestamp) = %s AND status = 'CLOSED'",
                (date_str,)
            )
            total = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return float(total)
    except Exception as e:
        logger.error(f"Failed to get daily P&L: {e}")
        return 0.0
