from datetime import datetime, timedelta
from sqlalchemy import select
from app.database.models import TestResultDB


def history(session, source_id, days=7):
    days = max(1, min(int(days), 365))
    return list(session.scalars(
        select(TestResultDB)
        .where(TestResultDB.source_id == source_id,
               TestResultDB.tested_at >= datetime.utcnow() - timedelta(days=days))
        .order_by(TestResultDB.tested_at.desc())
    ))


def summarize(rows):
    if not rows:
        return {'count': 0, 'availability': 0, 'failure_rate': 1,
                'average_latency': None, 'average_speed': None, 'average_score': None}
    # Quick checks have segment_valid=None and are not evidence of availability
    # or failure. Exclude them from quality metrics instead of treating them as
    # failures merely because they were part of the history window.
    validated = [r for r in rows if r.segment_valid is not None]
    successful = [r for r in validated if r.segment_valid is True]
    avg = lambda xs: sum(xs) / len(xs) if xs else None
    return {
        'count': len(rows),
        'validated_count': len(validated),
        'availability': len(successful) / len(validated) if validated else None,
        'failure_rate': 1 - len(successful) / len(validated) if validated else None,
        'average_latency': avg([r.ttfb for r in validated if r.ttfb is not None]),
        'average_speed': avg([r.download_speed for r in successful if r.download_speed is not None]),
        'average_score': avg([r.score for r in successful if r.score is not None]),
    }
