from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

import os
_db_path = "/data/health.db" if os.path.isdir("/data") else "./health.db"
engine = create_engine(f"sqlite:///{_db_path}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401 — ensures models are registered
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate():
    """Add columns that didn't exist in earlier schema versions."""
    new_cols = [
        ("activities", "zone1_secs", "INTEGER"),
        ("activities", "zone2_secs", "INTEGER"),
        ("activities", "zone3_secs", "INTEGER"),
        ("activities", "zone4_secs", "INTEGER"),
        ("activities", "zone5_secs", "INTEGER"),
    ]
    with engine.connect() as conn:
        for table, col, typ in new_cols:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))
                conn.commit()
            except Exception:
                pass  # column already exists
