from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(frozen=True)
class Event:
    name: str
    payload: dict
    created_at: datetime

    @classmethod
    def create(cls, name: str, payload: dict):
        return cls(name, payload, datetime.now(timezone.utc))
