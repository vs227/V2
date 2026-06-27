import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
from config import get_settings
from logger import setup_logger

logger = setup_logger("database")
settings = get_settings()


from psycopg2.pool import ThreadedConnectionPool

_pool = None

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
    if _pool is None:
        try:
            logger.info("Initializing database connection pool...")
            _pool = ThreadedConnectionPool(2, 20, settings.supabase_db_url)
            logger.info("Database connection pool initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database connection pool: {e}")
            return psycopg2.connect(settings.supabase_db_url)
            
    try:
        conn = _pool.getconn()
        return ConnectionProxy(conn, _pool)
    except Exception as e:
        logger.warning(f"Failed to get connection from pool: {e}. Falling back to direct connection.")
        return psycopg2.connect(settings.supabase_db_url)


def init_db() -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL,
            symbol TEXT NOT NULL,
            strike NUMERIC,
            expiry TEXT,
            option_type TEXT,
            entry_price NUMERIC,
            exit_price NUMERIC,
            quantity INTEGER NOT NULL,
            stoploss NUMERIC,
            target NUMERIC,
            pnl NUMERIC DEFAULT 0,
            gross_pnl NUMERIC DEFAULT 0,
            total_charges NUMERIC DEFAULT 0,
            brokerage NUMERIC DEFAULT 0,
            stt NUMERIC DEFAULT 0,
            transaction_charges NUMERIC DEFAULT 0,
            gst NUMERIC DEFAULT 0,
            sebi_fees NUMERIC DEFAULT 0,
            stamp_duty NUMERIC DEFAULT 0,
            strategy TEXT,
            reason TEXT,
            status TEXT DEFAULT 'OPEN',
            order_id TEXT,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
    logger.info("Database initialized")


def insert_trade(trade: dict) -> int:
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
    logger.info(f"Trade inserted: id={trade_id}, symbol={trade.get('symbol')}")
    return trade_id


def get_trade(trade_id: int) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    cursor.execute("SELECT * FROM trades WHERE id = %s", (trade_id,))
    trade = cursor.fetchone()
    cursor.close()
    conn.close()
    return dict(trade) if trade else None


def get_open_trades(symbol: str = None) -> list:
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


def get_all_trades(limit: int = 100, symbol: str = None) -> list:
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


def get_closed_trades(limit: int = 100, symbol: str = None) -> list:
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


def get_trades_by_date(date_str: str) -> list:
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


def update_trade(trade_id: int, updates: dict) -> bool:
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


def get_daily_pnl(date_str: str = None) -> float:
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
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
