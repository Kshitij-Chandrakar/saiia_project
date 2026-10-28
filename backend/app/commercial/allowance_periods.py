"""Calendar boundaries only; no grants, metering, persistence or enforcement."""
import calendar
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def allowance_period(now: datetime, signup: datetime, cadence: str):
    """Return half-open UTC boundaries, retaining the original IST signup day."""
    if now.tzinfo is None or signup.tzinfo is None or now < signup:
        raise ValueError("Invalid allowance timestamps")
    local = now.astimezone(IST)
    if cadence == "day":
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif cadence == "month":
        anchor = signup.astimezone(IST).day

        def boundary(index):
            year, month = divmod(index, 12)
            month += 1
            return datetime(year, month, min(anchor, calendar.monthrange(year, month)[1]), tzinfo=IST)

        index = local.year * 12 + local.month - 1
        if local < boundary(index):
            index -= 1
        start, end = boundary(index), boundary(index + 1)
    else:
        raise ValueError("Unsupported allowance cadence")
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
