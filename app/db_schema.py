"""
Car Lens — Full database schema.
Vehicle Master DB + Listings DB + Market Intelligence tables.
All created in Neon PostgreSQL via init_full_schema().
"""

VEHICLE_MASTER_TABLES = [
    # ── Manufacturers ──────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS manufacturers (
        id          SERIAL PRIMARY KEY,
        name        TEXT NOT NULL UNIQUE,
        slug        TEXT NOT NULL UNIQUE,
        country     TEXT DEFAULT 'India',
        active      BOOLEAN DEFAULT TRUE,
        created_at  TIMESTAMP DEFAULT NOW(),
        updated_at  TIMESTAMP DEFAULT NOW()
    )
    """,
    # ── Models ─────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS vehicle_models (
        id               SERIAL PRIMARY KEY,
        manufacturer_id  INTEGER REFERENCES manufacturers(id),
        name             TEXT NOT NULL,
        slug             TEXT NOT NULL,
        body_type        TEXT,
        segment          TEXT,
        active           BOOLEAN DEFAULT TRUE,
        first_year       INTEGER,
        latest_year      INTEGER,
        created_at       TIMESTAMP DEFAULT NOW(),
        updated_at       TIMESTAMP DEFAULT NOW(),
        UNIQUE(manufacturer_id, slug)
    )
    """,
    # ── Generations ────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS vehicle_generations (
        id                  SERIAL PRIMARY KEY,
        model_id            INTEGER REFERENCES vehicle_models(id),
        generation_name     TEXT,
        start_year          INTEGER,
        end_year            INTEGER,
        generation_metadata JSONB DEFAULT '{}',
        created_at          TIMESTAMP DEFAULT NOW()
    )
    """,
    # ── Model Years ────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS vehicle_years (
        id            SERIAL PRIMARY KEY,
        generation_id INTEGER REFERENCES vehicle_generations(id),
        model_year    INTEGER NOT NULL
    )
    """,
    # ── Variants ───────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS vehicle_variants (
        id                  SERIAL PRIMARY KEY,
        year_id             INTEGER REFERENCES vehicle_years(id),
        variant_name        TEXT NOT NULL,
        engine              TEXT,
        displacement        TEXT,
        fuel                TEXT,
        transmission        TEXT,
        power               TEXT,
        torque              TEXT,
        mileage             TEXT,
        range_km            TEXT,
        seating             INTEGER,
        boot_space          TEXT,
        airbags             INTEGER,
        safety_rating       TEXT,
        adas                JSONB DEFAULT '[]',
        features            JSONB DEFAULT '[]',
        ev_battery          TEXT,
        ev_claimed_range    TEXT,
        ev_charging_time    TEXT,
        ex_showroom_price   BIGINT,
        on_road_price       BIGINT,
        price_type          TEXT DEFAULT 'ex_showroom',
        source              TEXT DEFAULT 'manual',
        source_url          TEXT,
        observed_at         TIMESTAMP,
        last_updated_at     TIMESTAMP DEFAULT NOW(),
        created_at          TIMESTAMP DEFAULT NOW()
    )
    """,
]

LISTINGS_TABLES = [
    # ── Raw Feed Items ─────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS rss_feed_items (
        id              SERIAL PRIMARY KEY,
        guid            TEXT UNIQUE NOT NULL,
        title           TEXT,
        description     TEXT,
        url             TEXT,
        image_url       TEXT,
        published_at    TIMESTAMP,
        fetched_at      TIMESTAMP DEFAULT NOW(),
        processed       BOOLEAN DEFAULT FALSE,
        raw_xml         TEXT
    )
    """,
    # ── Listings ───────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS listings (
        id                      TEXT PRIMARY KEY,
        vehicle_variant_id      INTEGER REFERENCES vehicle_variants(id),
        source                  TEXT,
        source_url              TEXT,
        source_item_id          TEXT,
        title                   TEXT,
        description             TEXT,
        asking_price            BIGINT,
        kilometres              INTEGER,
        registration_year       INTEGER,
        manufacturing_year      INTEGER,
        brand                   TEXT,
        model                   TEXT,
        variant                 TEXT,
        fuel_type               TEXT,
        transmission            TEXT,
        color                   TEXT,
        ownership               TEXT,
        location                TEXT,
        seller_type             TEXT,
        seller_name             TEXT,
        images                  JSONB DEFAULT '[]',
        first_seen_at           TIMESTAMP DEFAULT NOW(),
        last_seen_at            TIMESTAMP DEFAULT NOW(),
        published_at            TIMESTAMP,
        listing_status          TEXT DEFAULT 'ACTIVE_OBSERVED',
        extraction_status       TEXT DEFAULT 'PENDING',
        vehicle_match_confidence TEXT DEFAULT 'NEEDS_VERIFICATION',
        groq_extracted          JSONB DEFAULT '{}',
        deal_score              INTEGER,
        fair_price_estimate     BIGINT,
        price_status            TEXT,
        created_at              TIMESTAMP DEFAULT NOW(),
        updated_at              TIMESTAMP DEFAULT NOW()
    )
    """,
    # ── Market Intelligence ────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS market_stats (
        id              SERIAL PRIMARY KEY,
        brand           TEXT NOT NULL,
        model           TEXT NOT NULL,
        year            INTEGER,
        fuel_type       TEXT,
        transmission    TEXT,
        location        TEXT,
        listing_count   INTEGER DEFAULT 0,
        price_min       BIGINT,
        price_max       BIGINT,
        price_median    BIGINT,
        price_avg       BIGINT,
        km_avg          INTEGER,
        computed_at     TIMESTAMP DEFAULT NOW(),
        UNIQUE(brand, model, year, fuel_type, transmission, location)
    )
    """,
]

# Seed data — Indian manufacturers
MANUFACTURER_SEED = [
    ("Maruti Suzuki", "maruti-suzuki", "Japan/India"),
    ("Hyundai", "hyundai", "South Korea"),
    ("Tata", "tata", "India"),
    ("Mahindra", "mahindra", "India"),
    ("Kia", "kia", "South Korea"),
    ("Toyota", "toyota", "Japan"),
    ("Honda", "honda", "Japan"),
    ("Renault", "renault", "France"),
    ("Volkswagen", "volkswagen", "Germany"),
    ("Skoda", "skoda", "Czech Republic"),
    ("MG", "mg", "UK/China"),
    ("Jeep", "jeep", "USA"),
    ("Nissan", "nissan", "Japan"),
    ("Citroen", "citroen", "France"),
    ("BYD", "byd", "China"),
    ("BMW", "bmw", "Germany"),
    ("Mercedes-Benz", "mercedes-benz", "Germany"),
    ("Audi", "audi", "Germany"),
    ("Volvo", "volvo", "Sweden"),
    ("Lexus", "lexus", "Japan"),
    ("Porsche", "porsche", "Germany"),
    ("Land Rover", "land-rover", "UK"),
    ("Jaguar", "jaguar", "UK"),
    ("Lamborghini", "lamborghini", "Italy"),
    ("Ferrari", "ferrari", "Italy"),
    ("Rolls-Royce", "rolls-royce", "UK"),
    ("Bentley", "bentley", "UK"),
]

# Seed data — Popular Indian models
MODEL_SEED = [
    # (manufacturer_slug, model_name, model_slug, body_type, segment, first_year, latest_year)
    ("maruti-suzuki", "Alto K10",       "alto-k10",       "Hatchback", "budget",       2022, 2026),
    ("maruti-suzuki", "Swift",          "swift",          "Hatchback", "premium_hatch", 2005, 2026),
    ("maruti-suzuki", "Baleno",         "baleno",         "Hatchback", "premium_hatch", 2015, 2026),
    ("maruti-suzuki", "Dzire",          "dzire",          "Sedan",     "compact_sedan", 2008, 2026),
    ("maruti-suzuki", "WagonR",         "wagon-r",        "Hatchback", "budget",       1999, 2026),
    ("maruti-suzuki", "Brezza",         "brezza",         "SUV",       "compact_suv",  2016, 2026),
    ("maruti-suzuki", "Ertiga",         "ertiga",         "MPV",       "mpv",          2012, 2026),
    ("maruti-suzuki", "Grand Vitara",   "grand-vitara",   "SUV",       "mid_suv",      2022, 2026),
    ("maruti-suzuki", "Fronx",          "fronx",          "SUV",       "compact_suv",  2023, 2026),
    ("maruti-suzuki", "Jimny",          "jimny",          "SUV",       "off_road",     2023, 2026),
    ("hyundai",       "Grand i10 Nios", "grand-i10-nios", "Hatchback", "budget",       2019, 2026),
    ("hyundai",       "i20",            "i20",            "Hatchback", "premium_hatch", 2008, 2026),
    ("hyundai",       "Aura",           "aura",           "Sedan",     "compact_sedan", 2020, 2026),
    ("hyundai",       "Verna",          "verna",          "Sedan",     "mid_sedan",    2006, 2026),
    ("hyundai",       "Venue",          "venue",          "SUV",       "compact_suv",  2019, 2026),
    ("hyundai",       "Creta",          "creta",          "SUV",       "compact_suv",  2015, 2026),
    ("hyundai",       "Alcazar",        "alcazar",        "SUV",       "mid_suv",      2021, 2026),
    ("hyundai",       "Tucson",         "tucson",         "SUV",       "mid_suv",      2005, 2026),
    ("hyundai",       "Ioniq 5",        "ioniq-5",        "SUV",       "electric",     2022, 2026),
    ("hyundai",       "Exter",          "exter",          "SUV",       "compact_suv",  2023, 2026),
    ("tata",          "Tiago",          "tiago",          "Hatchback", "budget",       2016, 2026),
    ("tata",          "Tiago EV",       "tiago-ev",       "Hatchback", "electric",     2023, 2026),
    ("tata",          "Altroz",         "altroz",         "Hatchback", "premium_hatch", 2020, 2026),
    ("tata",          "Punch",          "punch",          "SUV",       "compact_suv",  2021, 2026),
    ("tata",          "Punch EV",       "punch-ev",       "SUV",       "electric",     2024, 2026),
    ("tata",          "Nexon",          "nexon",          "SUV",       "compact_suv",  2017, 2026),
    ("tata",          "Nexon EV",       "nexon-ev",       "SUV",       "electric",     2020, 2026),
    ("tata",          "Harrier",        "harrier",        "SUV",       "mid_suv",      2019, 2026),
    ("tata",          "Safari",         "safari",         "SUV",       "mid_suv",      2021, 2026),
    ("tata",          "Curvv",          "curvv",          "SUV",       "mid_suv",      2024, 2026),
    ("tata",          "Curvv EV",       "curvv-ev",       "SUV",       "electric",     2024, 2026),
    ("mahindra",      "Bolero",         "bolero",         "SUV",       "utility",      2000, 2026),
    ("mahindra",      "Scorpio Classic","scorpio-classic", "SUV",      "mid_suv",      2002, 2026),
    ("mahindra",      "Scorpio-N",      "scorpio-n",      "SUV",       "mid_suv",      2022, 2026),
    ("mahindra",      "XUV300",         "xuv300",         "SUV",       "compact_suv",  2019, 2026),
    ("mahindra",      "XUV400",         "xuv400",         "SUV",       "electric",     2023, 2026),
    ("mahindra",      "XUV700",         "xuv700",         "SUV",       "mid_suv",      2021, 2026),
    ("mahindra",      "Thar",           "thar",           "SUV",       "off_road",     2010, 2026),
    ("mahindra",      "Thar Roxx",      "thar-roxx",      "SUV",       "off_road",     2024, 2026),
    ("mahindra",      "BE 6e",          "be-6e",          "SUV",       "electric",     2025, 2026),
    ("kia",           "Sonet",          "sonet",          "SUV",       "compact_suv",  2020, 2026),
    ("kia",           "Seltos",         "seltos",         "SUV",       "mid_suv",      2019, 2026),
    ("kia",           "Carens",         "carens",         "MPV",       "mpv",          2022, 2026),
    ("kia",           "EV6",            "ev6",            "SUV",       "electric",     2022, 2026),
    ("toyota",        "Glanza",         "glanza",         "Hatchback", "premium_hatch", 2019, 2026),
    ("toyota",        "Urban Cruiser Hyryder", "hyryder", "SUV",       "mid_suv",      2022, 2026),
    ("toyota",        "Innova Crysta",  "innova-crysta",  "MPV",       "mpv",          2016, 2026),
    ("toyota",        "Innova HyCross", "innova-hycross", "MPV",       "mpv",          2022, 2026),
    ("toyota",        "Fortuner",       "fortuner",       "SUV",       "large_suv",    2009, 2026),
    ("toyota",        "Camry",          "camry",          "Sedan",     "luxury_sedan", 2012, 2026),
    ("honda",         "Amaze",          "amaze",          "Sedan",     "compact_sedan", 2013, 2026),
    ("honda",         "City",           "city",           "Sedan",     "mid_sedan",    1998, 2026),
    ("honda",         "Elevate",        "elevate",        "SUV",       "mid_suv",      2023, 2026),
    ("renault",       "Kwid",           "kwid",           "Hatchback", "budget",       2015, 2026),
    ("renault",       "Triber",         "triber",         "MPV",       "mpv",          2019, 2026),
    ("renault",       "Kiger",          "kiger",          "SUV",       "compact_suv",  2021, 2026),
    ("volkswagen",    "Taigun",         "taigun",         "SUV",       "compact_suv",  2021, 2026),
    ("volkswagen",    "Virtus",         "virtus",         "Sedan",     "mid_sedan",    2022, 2026),
    ("skoda",         "Kushaq",         "kushaq",         "SUV",       "compact_suv",  2021, 2026),
    ("skoda",         "Slavia",         "slavia",         "Sedan",     "mid_sedan",    2022, 2026),
    ("skoda",         "Octavia",        "octavia",        "Sedan",     "premium_sedan", 2010, 2026),
    ("mg",            "Hector",         "hector",         "SUV",       "mid_suv",      2019, 2026),
    ("mg",            "Astor",          "astor",          "SUV",       "compact_suv",  2021, 2026),
    ("mg",            "Windsor EV",     "windsor-ev",     "SUV",       "electric",     2024, 2026),
    ("mg",            "ZS EV",          "zs-ev",          "SUV",       "electric",     2020, 2026),
    ("nissan",        "Magnite",        "magnite",        "SUV",       "compact_suv",  2020, 2026),
    ("jeep",          "Compass",        "compass",        "SUV",       "mid_suv",      2017, 2026),
    ("jeep",          "Meridian",       "meridian",       "SUV",       "large_suv",    2022, 2026),
    ("citroen",       "C3",             "c3",             "Hatchback", "budget",       2022, 2026),
    ("citroen",       "C3 Aircross",    "c3-aircross",    "SUV",       "compact_suv",  2023, 2026),
    ("byd",           "Atto 3",         "atto-3",         "SUV",       "electric",     2023, 2026),
    ("byd",           "Seal",           "seal",           "Sedan",     "electric",     2024, 2026),
    ("bmw",           "3 Series",       "3-series",       "Sedan",     "luxury_sedan", 2005, 2026),
    ("bmw",           "5 Series",       "5-series",       "Sedan",     "luxury_sedan", 2003, 2026),
    ("bmw",           "X1",             "x1",             "SUV",       "luxury_suv",   2011, 2026),
    ("bmw",           "X3",             "x3",             "SUV",       "luxury_suv",   2004, 2026),
    ("bmw",           "X5",             "x5",             "SUV",       "luxury_suv",   2004, 2026),
    ("mercedes-benz", "C-Class",        "c-class",        "Sedan",     "luxury_sedan", 2000, 2026),
    ("mercedes-benz", "E-Class",        "e-class",        "Sedan",     "luxury_sedan", 2000, 2026),
    ("mercedes-benz", "GLC",            "glc",            "SUV",       "luxury_suv",   2015, 2026),
    ("mercedes-benz", "GLE",            "gle",            "SUV",       "luxury_suv",   2015, 2026),
    ("audi",          "A4",             "a4",             "Sedan",     "luxury_sedan", 2005, 2026),
    ("audi",          "Q3",             "q3",             "SUV",       "luxury_suv",   2012, 2026),
    ("audi",          "Q5",             "q5",             "SUV",       "luxury_suv",   2009, 2026),
    ("audi",          "Q7",             "q7",             "SUV",       "luxury_suv",   2006, 2026),
    ("land-rover",    "Defender",       "defender",       "SUV",       "luxury_suv",   2020, 2026),
    ("land-rover",    "Range Rover",    "range-rover",    "SUV",       "luxury_suv",   2012, 2026),
    ("land-rover",    "Range Rover Sport", "range-rover-sport", "SUV", "luxury_suv",  2005, 2026),
    ("land-rover",    "Discovery Sport","discovery-sport","SUV",       "luxury_suv",   2015, 2026),
]
