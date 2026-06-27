import psycopg2
import socket
from urllib.parse import urlparse, unquote
from config import get_settings

settings = get_settings()

print("Testing Supabase database connection...")
print(f"DB URL: {settings.supabase_db_url}")

# Parse URL
url = urlparse(settings.supabase_db_url)
params = {
    'dbname': url.path[1:] if url.path else 'postgres',
    'user': unquote(url.username) if url.username else 'postgres',
    'password': unquote(url.password) if url.password else '',
    'host': url.hostname,
    'port': url.port or 5432,
    'connect_timeout': 10
}
print(f"\nParsed params: {params}")

# Try to get IPv4
try:
    addrs = socket.getaddrinfo(params['host'], None, socket.AF_INET)
    if addrs:
        params['hostaddr'] = addrs[0][4][0]
        print(f"Using hostaddr: {params['hostaddr']}")
except Exception as e:
    print(f"Could not get IPv4: {e}")

# Test connection
print("\nTrying to connect...")
try:
    conn = psycopg2.connect(**params)
    print("SUCCESS: Connected to Supabase!")
    cur = conn.cursor()
    cur.execute("SELECT version();")
    print(f"PostgreSQL version: {cur.fetchone()}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"FAILED: {e}")

