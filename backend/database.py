import os
from pathlib import Path

from sqlmodel import SQLModel, Session, create_engine

# Resolve the DB path relative to this file so it stays consistent
# no matter which directory uvicorn is launched from.
_DB_PATH = Path(__file__).parent / "ikb.db"
DATABASE_URL = f"sqlite:///{_DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},   # required for SQLite + FastAPI
)


def create_db_and_tables() -> None:
    """Create all tables defined in models.py."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency that yields a database session."""
    with Session(engine) as session:
        yield session
