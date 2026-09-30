from sqlalchemy import text
from app.database.database import Base, engine
from app.database import models

def init_db():
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        with engine.begin() as conn:
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(remote_playlists)"))}
            additions = {
                "consecutive_failures": "INTEGER DEFAULT 0",
                "auto_deleted_at": "DATETIME",
            }
            for name, definition in additions.items():
                if name not in cols:
                    conn.execute(text(f"ALTER TABLE remote_playlists ADD COLUMN {name} {definition}"))

if __name__ == "__main__":
    init_db()
