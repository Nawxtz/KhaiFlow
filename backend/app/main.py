from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import api_router
from app.core.database import Base, engine, SessionLocal

logger = logging.getLogger(__name__)


def run_migrations_and_seed():
    if os.getenv("PYTEST_CURRENT_TEST"):
        return

    try:
        base_dir = Path(__file__).resolve().parent.parent
        ini_candidates = [
            Path("alembic.ini"),
            base_dir / "alembic.ini",
            base_dir.parent / "backend" / "alembic.ini",
        ]
        ini_path = next((p for p in ini_candidates if p.exists()), None)
        if ini_path:
            logger.info(f"Running Alembic migrations from {ini_path}...")
            alembic_cfg = Config(str(ini_path))
            command.upgrade(alembic_cfg, "head")
            logger.info("Alembic migrations completed successfully.")
        else:
            logger.info("alembic.ini not found, creating tables via Base.metadata...")
            Base.metadata.create_all(bind=engine)
    except Exception as exc:
        logger.error(f"Migration error, falling back to Base.metadata: {exc}")
        try:
            Base.metadata.create_all(bind=engine)
        except Exception as e2:
            logger.error(f"Failed to create tables via metadata: {e2}")

    try:
        with SessionLocal() as db:
            result = db.execute(text("SELECT count(*) FROM inventory")).scalar()
            if result == 0:
                logger.info("Database empty, auto-seeding demo data...")
                scripts_dir = base_dir.parent / "scripts"
                import sys

                if str(scripts_dir) not in sys.path and scripts_dir.exists():
                    sys.path.insert(0, str(scripts_dir))
                try:
                    from seed_demo import seed_demo_data

                    seed_demo_data()
                    logger.info("Demo data seeded successfully.")
                except ImportError:
                    logger.warning("seed_demo module not found, skipping seed.")
    except Exception as exc:
        logger.warning(f"Auto-seed check: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations_and_seed()
    yield


app = FastAPI(
    title="KhaiFlow Commerce API",
    description="Backend API for KhaiFlow chat commerce system",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok"}
