from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine():
    url = get_settings().database_url
    is_sqlite = url.startswith("sqlite")
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///" )).parent.mkdir(parents=True, exist_ok=True)

    kwargs = {}
    if is_sqlite:
        # SQLite is used as a local, multi-request database.  WAL lets readers
        # continue while a writer commits, and busy_timeout prevents transient
        # writer contention from immediately becoming "database is locked".
        kwargs["connect_args"] = {
            "check_same_thread": False,
            "timeout": 30,
        }
    else:
        kwargs["connect_args"] = {}

    eng = create_engine(url, **kwargs)

    if is_sqlite:
        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    return eng


engine = _engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
