from datetime import datetime, timedelta

from .config import BUCKET_MINUTES


def bucket_bounds(ts: datetime) -> tuple[datetime, datetime]:
    floored_minute = (ts.minute // BUCKET_MINUTES) * BUCKET_MINUTES
    start = ts.replace(minute=floored_minute, second=0, microsecond=0)
    end = start + timedelta(minutes=BUCKET_MINUTES)
    return start, end


def bucket_filename(ts: datetime) -> str:
    start, end = bucket_bounds(ts)
    return f"{start:%H%M}-{end:%H%M}.txt"


def bucket_day_dir(ts: datetime) -> str:
    return f"{ts:%Y-%m-%d}"
