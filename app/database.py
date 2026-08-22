"""
Neon PostgreSQL connection using requests (HTTP API).
No psycopg2 or SQLAlchemy needed.
"""
import os
import json
import logging
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

_db_available = False
_conn = None

# Try native psycopg2 first, fall back to requests-based HTTP if unavailable
try:
    import psycopg2
    import psycopg2.extras

    def get_connection():
        return psycopg2.connect(DATABASE_URL)

    def execute_query(sql: str, params=None, fetch=True):
        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, params or ())
            if fetch:
                rows = cur.fetchall()
                conn.close()
                return [dict(r) for r in rows]
            else:
                conn.commit()
                conn.close()
                return []
        except Exception as e:
            logger.error(f"DB query failed: {e}")
            raise

    _db_available = True
    logger.info("Database: psycopg2 connected to Neon PostgreSQL")

except ImportError:
    # Fall back to Neon HTTP API
    try:
        parsed = urlparse(DATABASE_URL.replace("postgresql://", "https://").split("?")[0])
        _neon_user = parsed.username
        _neon_password = parsed.password
        _neon_host = parsed.hostname
        _neon_db = parsed.path.lstrip("/")
        _neon_http_url = f"https://{_neon_host}/sql"

        def execute_query(sql: str, params=None, fetch=True):
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Neon-Connection-String": DATABASE_URL,
                }
                body = {"query": sql, "params": list(params) if params else []}
                resp = requests.post(
                    _neon_http_url,
                    json=body,
                    headers=headers,
                    timeout=10,
                    verify=False,
                )
                resp.raise_for_status()
                data = resp.json()
                if fetch:
                    rows = data.get("rows", [])
                    return rows
                return []
            except Exception as e:
                logger.error(f"Neon HTTP query failed: {e}")
                raise

        _db_available = True
        logger.info("Database: Neon HTTP API connected")

    except Exception as e:
        logger.warning(f"Database unavailable: {e}")
        _db_available = False


def init_db():
    """Create tables if they don't exist."""
    if not _db_available:
        logger.warning("DB not available, skipping init")
        return

    tables = [
        """
        CREATE TABLE IF NOT EXISTS saved_analyses (
            id TEXT PRIMARY KEY,
            user_session TEXT,
            vehicle_brand TEXT,
            vehicle_model TEXT,
            vehicle_year INTEGER,
            vehicle_variant TEXT,
            asking_price BIGINT,
            fair_price_avg BIGINT,
            deal_score INTEGER,
            recommendation TEXT,
            full_data JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            saved_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY,
            session_id TEXT,
            role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
    ]

    for sql in tables:
        try:
            execute_query(sql.strip(), fetch=False)
            logger.info("DB table initialized")
        except Exception as e:
            logger.error(f"Table init failed: {e}")


def save_analysis(analysis_id: str, data: dict, session: str = "default"):
    """Save a car analysis to DB."""
    if not _db_available:
        return False
    try:
        vehicle = data.get("vehicle", {})
        execute_query(
            """
            INSERT INTO saved_analyses
                (id, user_session, vehicle_brand, vehicle_model, vehicle_year,
                 vehicle_variant, asking_price, fair_price_avg, deal_score, recommendation, full_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                full_data = EXCLUDED.full_data,
                saved_at = NOW()
            """,
            (
                analysis_id,
                session,
                vehicle.get("brand", ""),
                vehicle.get("model", ""),
                vehicle.get("year", 0),
                vehicle.get("variant", ""),
                data.get("askingPrice", 0),
                data.get("fairPrice", {}).get("avg", 0),
                data.get("dealScore", {}).get("overall", 0),
                data.get("recommendation", ""),
                json.dumps(data),
            ),
            fetch=False,
        )
        return True
    except Exception as e:
        logger.error(f"save_analysis failed: {e}")
        return False


def get_saved_analyses(session: str = "default", limit: int = 50):
    """Get all saved analyses."""
    if not _db_available:
        return []
    try:
        rows = execute_query(
            "SELECT full_data FROM saved_analyses WHERE user_session = %s ORDER BY saved_at DESC LIMIT %s",
            (session, limit),
        )
        return [json.loads(r["full_data"]) if isinstance(r.get("full_data"), str) else r.get("full_data", {}) for r in rows]
    except Exception as e:
        logger.error(f"get_saved failed: {e}")
        return []


def delete_analysis(analysis_id: str):
    """Delete a saved analysis."""
    if not _db_available:
        return False
    try:
        execute_query("DELETE FROM saved_analyses WHERE id = %s", (analysis_id,), fetch=False)
        return True
    except Exception as e:
        logger.error(f"delete_analysis failed: {e}")
        return False
