"""Database Connection & Session Management."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings
from app.db.models import Base
import logging

logger = logging.getLogger(__name__)

# Connect args for SQLite if used
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

# Primary Engine (Read-Write)
engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Read-Only Engine
readonly_url = settings.READONLY_DATABASE_URL or settings.DATABASE_URL
ro_connect_args = {"check_same_thread": False} if readonly_url.startswith("sqlite") else {}

readonly_engine = create_engine(
    readonly_url,
    connect_args=ro_connect_args,
    pool_pre_ping=True
)

ReadOnlySessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=readonly_engine)

def get_db():
    """Dependency for read-write DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_readonly_db():
    """Dependency for read-only DB session."""
    db = ReadOnlySessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized successfully.")
