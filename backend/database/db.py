import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from database.models import Base
from config import DB_PATH

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{DB_PATH}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _engine


def init_db():
    """Create all tables if they don't exist yet."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        engine = init_db()
        _SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return _SessionLocal()
