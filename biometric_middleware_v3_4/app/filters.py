from datetime import datetime


def parse_dt(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip().replace("Z", "+00:00")
    d = datetime.fromisoformat(s)
    return d.replace(tzinfo=None)


def filter_events(events, from_date=None, to_date=None, employee_ids=None):
    """Filter normalized events.

    employee_ids semantics are intentionally strict:
    - None: do not filter by employee (legacy/manual mode only).
    - []: allow no employees.
    - [ids...]: allow only those external employee IDs.
    """
    start = parse_dt(from_date)
    end = parse_dt(to_date)
    allowed = (
        None
        if employee_ids is None
        else {str(x).strip() for x in employee_ids}
    )

    out = []
    for event in events:
        dt = parse_dt(event["event_time"])
        employee_code = str(event.get("employee_code") or "").strip()

        if start and dt < start:
            continue
        if end and dt > end:
            continue
        if allowed is not None and employee_code not in allowed:
            continue
        out.append(event)

    return out
