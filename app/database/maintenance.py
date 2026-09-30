from datetime import datetime, timedelta
from sqlalchemy import delete
from app.core.config import get_settings
from app.database.database import SessionLocal
from app.database.models import TestResultDB
from app.database.locks import db_write_lock


def cleanup_old_test_results() -> int:
    cutoff = datetime.utcnow() - timedelta(days=get_settings().history_retention_days)
    with SessionLocal() as session:
        result = session.execute(delete(TestResultDB).where(TestResultDB.tested_at < cutoff))
        session.commit()
        return int(result.rowcount or 0)
