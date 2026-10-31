from datetime import datetime
import pytest
from app.commercial.allowance_periods import allowance_period


@pytest.mark.parametrize("year,day,feb", [(2025, 29, 28), (2025, 30, 28), (2025, 31, 28), (2024, 29, 29), (2024, 30, 29), (2024, 31, 29)])
def test_month_anchor_restored(year, day, feb):
    signup = datetime.fromisoformat(f"{year}-01-{day}T10:00:00+05:30")
    now = datetime.fromisoformat(f"{year}-02-{feb}T00:00:00+05:30")
    start, end = allowance_period(now, signup, "month")
    assert start == now
    assert end == datetime.fromisoformat(f"{year}-03-{day}T00:00:00+05:30")


def test_daily_and_monthly_independent_and_exact_boundary():
    signup = datetime.fromisoformat("2025-01-31T10:00:00+05:30")
    now = datetime.fromisoformat("2025-04-15T00:00:00+05:30")
    daily = allowance_period(now, signup, "day")
    monthly = allowance_period(now, signup, "month")
    assert daily == (now, datetime.fromisoformat("2025-04-16T00:00:00+05:30"))
    assert monthly == (datetime.fromisoformat("2025-03-31T00:00:00+05:30"), datetime.fromisoformat("2025-04-30T00:00:00+05:30"))
    assert allowance_period(daily[1], signup, "day")[0] == daily[1]


def test_invalid_timestamps_and_cadence():
    now = datetime.fromisoformat("2025-04-15T00:00:00+05:30")
    for args in [(now.replace(tzinfo=None), now, "day"), (now, now, "year")]:
        with pytest.raises(ValueError):
            allowance_period(*args)


def test_signup_day_is_derived_in_ist_not_utc():
    signup=datetime.fromisoformat('2025-01-30T20:00:00+00:00')  # Jan31 IST
    now=datetime.fromisoformat('2025-02-28T18:30:00+00:00')  # Mar1 midnight IST
    assert allowance_period(now,signup,'month') == (datetime.fromisoformat('2025-02-28T00:00:00+05:30'),datetime.fromisoformat('2025-03-31T00:00:00+05:30'))
    assert allowance_period(now,signup,'day')[0]==now
