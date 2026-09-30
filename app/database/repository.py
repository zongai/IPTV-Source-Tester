from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database.models import ChannelDB, SourceDB

class Repository:
    def __init__(self, session: Session):
        self.session = session

    def get_channel(self, channel_id: str):
        return self.session.get(ChannelDB, channel_id)

    def get_source(self, source_id: int):
        return self.session.get(SourceDB, source_id)

    def list_sources(self, channel_id: str | None = None):
        stmt = select(SourceDB)
        if channel_id:
            stmt = stmt.where(SourceDB.channel_id == channel_id)
        return list(self.session.scalars(stmt))
