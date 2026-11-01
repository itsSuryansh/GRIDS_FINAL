"""Database engine/session helpers (SQLite + SQLAlchemy 2.x)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.database import Base


def _make_engine(url: str | None = None) -> Engine:
    url = url or settings.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    eng = create_engine(url, echo=settings.echo_sql, connect_args=connect_args, future=True)
    if url.startswith("sqlite"):

        @event.listens_for(eng, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # pragma: no cover
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    return eng


engine: Engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def init_db(bind: Engine | None = None) -> None:
    Base.metadata.create_all(bind=bind or engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
