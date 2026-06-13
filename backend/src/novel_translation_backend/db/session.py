from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def _database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")
    return database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create one shared engine the first time database access is needed."""
    return create_engine(_database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Create one shared factory for short-lived transactional sessions."""
    return sessionmaker(
        bind=get_engine(),
        class_=Session,
        expire_on_commit=False,
    )
