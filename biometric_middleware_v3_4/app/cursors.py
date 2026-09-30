from datetime import timedelta

from .filters import parse_dt


def compute_fetch_start(floor, cursor=None, overlap_minutes=360):
    """Compute a safe device fetch start.

    - floor is the earliest allowed production/backfill timestamp.
    - cursor is the end timestamp of the last successfully persisted fetch.
    - overlap intentionally re-reads a safety window; event_key deduplication
      makes this safe and protects against edge/boundary timing issues.
    """
    floor_dt = parse_dt(floor)
    if floor_dt is None:
        raise ValueError("fetch floor is required")

    if not cursor:
        return floor_dt

    cursor_dt = parse_dt(cursor)
    if cursor_dt is None:
        return floor_dt

    overlap = max(0, int(overlap_minutes))
    candidate = cursor_dt - timedelta(minutes=overlap)
    return max(floor_dt, candidate)
