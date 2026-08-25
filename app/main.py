import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="CARVIEW_AI - Used Car Analysis Backend",
    description=(
        "Comprehensive used car valuation and analysis API tailored for the Indian automotive market. "
        "Provides fair pricing via depreciation-heuristic engine, Groq LLM-powered listing intelligence, "
        "Gemini image-based condition assessment, risk signaling, negotiation strategy, and multi-vehicle comparison."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

cors_origins_env = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,https://carlensai.netlify.app",
)
origins = [o.strip().rstrip("/") for o in cors_origins_env.split(",") if o.strip()]

required_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://carlensai.netlify.app",
]
for origin in required_origins:
    if origin not in origins:
        origins.append(origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.netlify\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Analysis-ID"],
    max_age=3600
)

@app.get("/", tags=["root"])
async def root():
    return {
        "name": "CARVIEW_AI Used Car Analysis API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/api/health",
        "endpoints": {
            "full_analysis": "POST /api/analyze",
            "listing_only": "POST /api/analyze/listing",
            "image_analysis": "POST /api/analyze/images",
            "compare": "POST /api/compare",
            "save": "POST /api/save",
            "negotiate": "POST /api/negotiate",
            "health": "GET /api/health",
            "sample": "GET /api/sample"
        }
    }


app.include_router(api_router)


@app.on_event("startup")
async def startup_event():
    logger.info("CARVIEW_AI Backend starting up...")
    logger.info(f"CORS origins configured: {origins}")

    from app.services import groq_service, gemini_service
    from app.database import init_db, _db_available

    if groq_service._groq_available:
        logger.info("Groq LLM integration: ACTIVE (model: llama-3.3-70b-versatile)")
    else:
        logger.warning("Groq LLM integration: UNAVAILABLE - using heuristic + mock fallback")

    if gemini_service._genai_configured:
        logger.info("Google Gemini image analysis: ACTIVE (model: gemini-flash-latest)")
    else:
        logger.warning("Google Gemini image analysis: UNAVAILABLE - using mock image inspection profiles")

    # Init Neon DB
    try:
        init_db()
        if _db_available:
            logger.info("Neon PostgreSQL: CONNECTED ✓")
        else:
            logger.warning("Neon PostgreSQL: UNAVAILABLE - using in-memory fallback")
    except Exception as e:
        logger.warning(f"DB init failed: {e}")

    logger.info("Startup complete. CARVIEW_AI backend ready.")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("CARVIEW_AI Backend shutting down...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
