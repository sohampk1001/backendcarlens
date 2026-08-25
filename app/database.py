"""
Car Lens — Neon PostgreSQL database layer.
Handles vehicle master DB + listings DB + market stats + saved analyses.
"""
import os
import json
import logging
import re
import requests
import warnings
from dotenv import load_dotenv
from app.db_schema import VEHICLE_MASTER_TABLES, LISTINGS_TABLES, MANUFACTURER_SEED, MODEL_SEED

load_dotenv()
logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL", "")

_db_available = False

# ── Connection ─────────────────────────────────────────────────────────────────

try:
    import psycopg2
    import psycopg2.extras

    def _get_conn():
        return psycopg2.connect(DATABASE_URL)

    def execute_query(sql: str, params=None, fetch=True):
        conn = _get_conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, params or ())
            if fetch:
                rows = cur.fetchall()
                conn.commit()
                return [dict(r) for r in rows]
            conn.commit()
            return []
        except Exception as e:
            conn.rollback()
            logger.error(f"DB query failed: {e}")
            raise
        finally:
            conn.close()

    _db_available = True
    logger.info("Database: psycopg2 connected")

except ImportError:
    try:
        from urllib.parse import urlparse
        _host = urlparse(DATABASE_URL.split("?")[0]).hostname
        _neon_http_url = f"https://{_host}/sql"

        def execute_query(sql: str, params=None, fetch=True):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                headers = {"Content-Type": "application/json", "Neon-Connection-String": DATABASE_URL}
                # Convert named parameters to positional for Neon HTTP API
                if params:
                    # Replace %s with $1, $2, etc. for Neon HTTP API
                    param_count = 0
                    def replace_placeholder(match):
                        nonlocal param_count
                        param_count += 1
                        return f"${param_count}"
                    sql = re.sub(r'%s', replace_placeholder, sql)
                    body = {"query": sql, "params": list(params) if params else []}
                else:
                    body = {"query": sql, "params": []}
                resp = requests.post(_neon_http_url, json=body, headers=headers, timeout=15, verify=False)
                resp.raise_for_status()
                data = resp.json()
                return data.get("rows", []) if fetch else []

        _db_available = True
        logger.info("Database: Neon HTTP API connected")
    except Exception as e:
        logger.warning(f"Database unavailable: {e}")

        def execute_query(sql, params=None, fetch=True):
            logger.warning("DB not available — query skipped")
            return []


# ── Schema Init ────────────────────────────────────────────────────────────────

def init_db():
    if not _db_available:
        return
    all_tables = VEHICLE_MASTER_TABLES + LISTINGS_TABLES + [
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
    for sql in all_tables:
        try:
            execute_query(sql.strip(), fetch=False)
        except Exception as e:
            logger.error(f"Table init failed: {e}")
    
    # Add feed_type column to rss_feed_items if it doesn't exist
    try:
        execute_query(
            "ALTER TABLE rss_feed_items ADD COLUMN IF NOT EXISTS feed_type TEXT DEFAULT 'used_cars'",
            fetch=False
        )
    except Exception as e:
        logger.warning(f"Failed to add feed_type column to rss_feed_items: {e}")
    
    # Add feed_type column to listings if it doesn't exist
    try:
        execute_query(
            "ALTER TABLE listings ADD COLUMN IF NOT EXISTS feed_type TEXT",
            fetch=False
        )
    except Exception as e:
        logger.warning(f"Failed to add feed_type column to listings: {e}")
    
    logger.info("DB schema initialized")
    _seed_manufacturers()
    _seed_models()


def _seed_manufacturers():
    try:
        existing = execute_query("SELECT COUNT(*) as c FROM manufacturers")
        count = int(existing[0].get("c", 0)) if existing else 0
        if count > 0:
            return
        for name, slug, country in MANUFACTURER_SEED:
            try:
                execute_query(
                    "INSERT INTO manufacturers (name, slug, country) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                    (name, slug, country), fetch=False
                )
            except Exception:
                pass
        logger.info(f"Seeded {len(MANUFACTURER_SEED)} manufacturers")
    except Exception as e:
        logger.warning(f"Manufacturer seed failed: {e}")


def _seed_models():
    try:
        existing = execute_query("SELECT COUNT(*) as c FROM vehicle_models")
        count = int(existing[0].get("c", 0)) if existing else 0
        if count > 0:
            return
        for mfr_slug, model_name, model_slug, body_type, segment, first_yr, latest_yr in MODEL_SEED:
            try:
                mfr = execute_query("SELECT id FROM manufacturers WHERE slug = $1", (mfr_slug,))
                if not mfr:
                    continue
                mfr_id = mfr[0]["id"]
                execute_query(
                    """INSERT INTO vehicle_models
                       (manufacturer_id, name, slug, body_type, segment, first_year, latest_year)
                       VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT DO NOTHING""",
                    (mfr_id, model_name, model_slug, body_type, segment, first_yr, latest_yr),
                    fetch=False
                )
            except Exception:
                pass
        logger.info(f"Seeded {len(MODEL_SEED)} models")
    except Exception as e:
        logger.warning(f"Model seed failed: {e}")


# ── Vehicle Discovery ──────────────────────────────────────────────────────────

def get_all_manufacturers(active_only=True):
    try:
        sql = "SELECT id, name, slug, country FROM manufacturers"
        if active_only:
            sql += " WHERE active = TRUE"
        sql += " ORDER BY name"
        return execute_query(sql, [])
    except Exception as e:
        logger.error(f"get_all_manufacturers: {e}")
        return []


def get_models_by_manufacturer(manufacturer_slug: str):
    try:
        return execute_query(
            """SELECT vm.id, vm.name, vm.slug, vm.body_type, vm.segment,
                      vm.first_year, vm.latest_year
               FROM vehicle_models vm
               JOIN manufacturers m ON vm.manufacturer_id = m.id
               WHERE m.slug = $1 AND vm.active = TRUE
               ORDER BY vm.name""",
            (manufacturer_slug,)
        )
    except Exception as e:
        logger.error(f"get_models_by_manufacturer: {e}")
        return []


def get_model_years(model_slug: str, manufacturer_slug: str):
    try:
        return execute_query(
            """SELECT DISTINCT vy.model_year
               FROM vehicle_years vy
               JOIN vehicle_generations vg ON vy.generation_id = vg.id
               JOIN vehicle_models vm ON vg.model_id = vm.id
               JOIN manufacturers m ON vm.manufacturer_id = m.id
               WHERE vm.slug = $1 AND m.slug = $2
               ORDER BY vy.model_year DESC""",
            (model_slug, manufacturer_slug)
        )
    except Exception as e:
        logger.error(f"get_model_years: {e}")
        return []


def get_variants(model_slug: str, year: int):
    try:
        return execute_query(
            """SELECT vv.*
               FROM vehicle_variants vv
               JOIN vehicle_years vy ON vv.year_id = vy.id
               JOIN vehicle_generations vg ON vy.generation_id = vg.id
               JOIN vehicle_models vm ON vg.model_id = vm.id
               WHERE vm.slug = $1 AND vy.model_year = $2
               ORDER BY vv.ex_showroom_price""",
            (model_slug, year)
        )
    except Exception as e:
        logger.error(f"get_variants: {e}")
        return []


# ── Listings ───────────────────────────────────────────────────────────────────

def get_listings(brand: str = None, model: str = None, year: int = None,
                 fuel: str = None, transmission: str = None,
                 location: str = None, min_price: int = None,
                 max_price: int = None, max_km: int = None,
                 feed_type: str = None,
                 limit: int = 50, offset: int = 0):
    try:
        conditions = ["listing_status = 'ACTIVE_OBSERVED'"]
        params = []
        param_count = 0
        
        def add_param(value):
            nonlocal param_count
            param_count += 1
            params.append(value)
            return f"${param_count}"
        
        if brand:
            conditions.append(f"LOWER(brand) = LOWER({add_param(str(brand))})")
        if model:
            conditions.append(f"LOWER(model) LIKE LOWER({add_param(f'%{model}%')})")
        if year:
            conditions.append(f"manufacturing_year = {add_param(int(year))}")
        if fuel:
            conditions.append(f"LOWER(fuel_type) = LOWER({add_param(str(fuel))})")
        if transmission:
            conditions.append(f"LOWER(transmission) = LOWER({add_param(str(transmission))})")
        if location:
            conditions.append(f"LOWER(location) LIKE LOWER({add_param(f'%{location}%')})")
        if min_price:
            conditions.append(f"asking_price >= {add_param(int(min_price))}")
        if max_price:
            conditions.append(f"asking_price <= {add_param(int(max_price))}")
        if max_km:
            conditions.append(f"kilometres <= {add_param(int(max_km))}")
        if feed_type:
            conditions.append(f"feed_type = {add_param(str(feed_type))}")

        where = " AND ".join(conditions)
        params.extend([int(limit), int(offset)])
        param_count += 2
        
        return execute_query(
            f"""SELECT id, title, brand, model, variant, manufacturing_year,
                       registration_year, asking_price, kilometres, fuel_type,
                       transmission, color, ownership, location, seller_type,
                       images, listing_status, deal_score, fair_price_estimate,
                       price_status, source, source_url, first_seen_at, last_seen_at, feed_type
                FROM listings WHERE {where}
                ORDER BY last_seen_at DESC LIMIT ${param_count-1} OFFSET ${param_count}""",
            params
        )
    except Exception as e:
        logger.error(f"get_listings: {e}")
        return []


def get_listing_count(brand: str = None, model: str = None, year: int = None) -> int:
    try:
        conditions = ["listing_status = 'ACTIVE_OBSERVED'"]
        params = []
        param_count = 0
        
        def add_param(value):
            nonlocal param_count
            param_count += 1
            params.append(value)
            return f"${param_count}"
        
        if brand:
            conditions.append(f"LOWER(brand) = LOWER({add_param(brand)})")
        if model:
            conditions.append(f"LOWER(model) LIKE LOWER({add_param(f'%{model}%')})")
        if year:
            conditions.append(f"manufacturing_year = {add_param(year)}")
        
        where = " AND ".join(conditions)
        rows = execute_query(f"SELECT COUNT(*) as c FROM listings WHERE {where}", params)
        return rows[0].get("c", 0) if rows else 0
    except Exception as e:
        logger.error(f"get_listing_count: {e}")
        return 0


def upsert_listing(listing: dict):
    try:
        # Convert %s to $1, $2, etc. for Neon HTTP API
        sql = """INSERT INTO listings
               (id, source, source_url, source_item_id, title, description,
                asking_price, kilometres, registration_year, manufacturing_year,
                brand, model, variant, fuel_type, transmission, color, ownership,
                location, seller_type, images, published_at, listing_status,
                extraction_status, groq_extracted, feed_type)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25)
               ON CONFLICT (id) DO UPDATE SET
                 last_seen_at = NOW(),
                 listing_status = EXCLUDED.listing_status,
                 asking_price = EXCLUDED.asking_price,
                 groq_extracted = EXCLUDED.groq_extracted,
                 feed_type = EXCLUDED.feed_type,
                 updated_at = NOW()"""
        
        # Include feed_type in source for RSS items
        source = listing.get("source", "unknown")
        feed_type = listing.get("feed_type")
        if feed_type and source == "rss_feed":
            source = f"rss_feed_{feed_type}"
        
        params = (
            listing.get("id"), source, listing.get("source_url"),
            listing.get("source_item_id"), listing.get("title"), listing.get("description"),
            listing.get("asking_price"), listing.get("kilometres"), listing.get("registration_year"),
            listing.get("manufacturing_year"), listing.get("brand"), listing.get("model"),
            listing.get("variant"), listing.get("fuel_type"), listing.get("transmission"),
            listing.get("color"), listing.get("ownership"), listing.get("location"),
            listing.get("seller_type"), json.dumps(listing.get("images", [])),
            listing.get("published_at"), listing.get("listing_status", "ACTIVE_OBSERVED"),
            listing.get("extraction_status", "PENDING"),
            json.dumps(listing.get("groq_extracted", {})),
            feed_type,
        )
        
        execute_query(sql, params, fetch=False)
        return True
    except Exception as e:
        logger.error(f"upsert_listing: {e}")
        return False


def get_market_stats(brand: str, model: str, year: int = None):
    try:
        params = [brand.lower(), f"%{model.lower()}%"]
        sql = """SELECT COUNT(*) as count,
                        MIN(asking_price) as min_price,
                        MAX(asking_price) as max_price,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY asking_price) as median_price,
                        AVG(asking_price)::BIGINT as avg_price,
                        AVG(kilometres)::INTEGER as avg_km
                 FROM listings
                 WHERE listing_status = 'ACTIVE_OBSERVED'
                   AND LOWER(brand) = $1 AND LOWER(model) LIKE $2"""
        if year:
            sql += " AND manufacturing_year = $3"
            params.append(year)
        rows = execute_query(sql, params)
        return rows[0] if rows else {}
    except Exception as e:
        logger.error(f"get_market_stats: {e}")
        return {}


# ── RSS Feed ───────────────────────────────────────────────────────────────────

def rss_item_exists(guid: str) -> bool:
    try:
        rows = execute_query("SELECT id FROM rss_feed_items WHERE guid = $1", (guid,))
        return len(rows) > 0
    except Exception:
        return False


def insert_rss_item(item: dict):
    try:
        execute_query(
            """INSERT INTO rss_feed_items (guid, title, description, url, image_url, published_at, raw_xml, feed_type)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8) ON CONFLICT (guid) DO NOTHING""",
            (item.get("guid"), item.get("title"), item.get("description"),
             item.get("url"), item.get("image_url"), item.get("published_at"), item.get("raw_xml"),
             item.get("feed_type", "used_cars")),
            fetch=False
        )
        return True
    except Exception as e:
        logger.error(f"insert_rss_item: {e}")
        return False


def get_unprocessed_rss_items(limit=20):
    try:
        return execute_query(
            "SELECT * FROM rss_feed_items WHERE processed = FALSE ORDER BY fetched_at ASC LIMIT $1",
            (limit,)
        )
    except Exception as e:
        logger.error(f"get_unprocessed_rss_items: {e}")
        return []


def mark_rss_item_processed(item_id: int):
    try:
        execute_query("UPDATE rss_feed_items SET processed = TRUE WHERE id = $1", (item_id,), fetch=False)
    except Exception as e:
        logger.error(f"mark_rss_item_processed: {e}")


# ── Saved Analyses ─────────────────────────────────────────────────────────────

def save_analysis(analysis_id: str, data: dict, session: str = "default"):
    if not _db_available:
        return False
    try:
        vehicle = data.get("vehicle", {})
        execute_query(
            """INSERT INTO saved_analyses
               (id, user_session, vehicle_brand, vehicle_model, vehicle_year,
                vehicle_variant, asking_price, fair_price_avg, deal_score, recommendation, full_data)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
               ON CONFLICT (id) DO UPDATE SET
                 full_data = EXCLUDED.full_data, saved_at = NOW()""",
            (analysis_id, session, vehicle.get("brand",""), vehicle.get("model",""),
             vehicle.get("year", 0), vehicle.get("variant",""),
             data.get("askingPrice", 0), data.get("fairPrice", {}).get("avg", 0),
             data.get("dealScore", {}).get("overall", 0), data.get("recommendation",""),
             json.dumps(data)),
            fetch=False
        )
        return True
    except Exception as e:
        logger.error(f"save_analysis failed: {e}")
        return False


def get_saved_analyses(session: str = "default", limit: int = 50):
    if not _db_available:
        return []
    try:
        rows = execute_query(
            "SELECT full_data FROM saved_analyses WHERE user_session = $1 ORDER BY saved_at DESC LIMIT $2",
            (session, limit)
        )
        result = []
        for r in rows:
            fd = r.get("full_data")
            if isinstance(fd, str):
                result.append(json.loads(fd))
            elif isinstance(fd, dict):
                result.append(fd)
        return result
    except Exception as e:
        logger.error(f"get_saved_analyses: {e}")
        return []


def delete_analysis(analysis_id: str):
    if not _db_available:
        return False
    try:
        execute_query("DELETE FROM saved_analyses WHERE id = $1", (analysis_id,), fetch=False)
        return True
    except Exception as e:
        logger.error(f"delete_analysis: {e}")
        return False
