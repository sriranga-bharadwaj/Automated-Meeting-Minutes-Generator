
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./ammg.db"

# SQLite handles many readers and one writer. The default pool (5 connections, 10 extra) ran out
# when 100 people used the app at once, so the pool is larger and waiting is allowed to last longer.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_size=30,
    max_overflow=70,
    pool_timeout=60,
)


@event.listens_for(engine, "connect")
def _sqlite_settings(dbapi_connection, _record):
    """WAL lets readers continue while one connection writes; busy_timeout waits for a lock instead of failing."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema():
    """Add columns introduced after an existing local ammg.db was created."""
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(meetings)")}
        if cols and "details_json" not in cols:
            conn.exec_driver_sql("ALTER TABLE meetings ADD COLUMN details_json TEXT")
        if cols and "owner_id" not in cols:
            conn.exec_driver_sql("ALTER TABLE meetings ADD COLUMN owner_id TEXT")
        # The role called "user" is now "organizer" (roles are admin, organizer, participant).
        if conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE name = 'users'").first():
            conn.exec_driver_sql("UPDATE users SET role = 'organizer' WHERE role = 'user'")
