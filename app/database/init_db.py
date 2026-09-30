from sqlalchemy import text
from app.database.database import Base, engine
from app.database import models

def init_db():
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        with engine.begin() as conn:
            # remote_playlists auto-delete columns
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(remote_playlists)"))}
            for name, definition in {
                "consecutive_failures": "INTEGER DEFAULT 0",
                "auto_deleted_at": "DATETIME",
            }.items():
                if name not in cols:
                    conn.execute(text(f"ALTER TABLE remote_playlists ADD COLUMN {name} {definition}"))
            # sources: per-entry group-title (fixes wrong channel-level grouping)
            src_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(sources)"))}
            if "group_name" not in src_cols:
                conn.execute(text("ALTER TABLE sources ADD COLUMN group_name VARCHAR(255)"))
                # Backfill from channel group when source group is empty
                conn.execute(text(
                    "UPDATE sources SET group_name = ("
                    "SELECT channels.group_name FROM channels WHERE channels.id = sources.channel_id"
                    ") WHERE group_name IS NULL OR group_name = ''"
                ))

if __name__ == "__main__":
    init_db()
