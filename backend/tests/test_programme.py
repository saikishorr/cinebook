"""Programmes are reproducible and respect runtime, coverage, prices and existing intervals."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.programme import generate_programme, prices

ZONE = ZoneInfo("Asia/Kolkata")
DAY = date(2030, 1, 7)  # Monday, so base-price bounds can be checked directly.


def screens(count=12):
    return [{"id": i, "cinema_id": i // 6, "chain": "PVR INOX", "format": "2D", "screens_count": 6}
            for i in range(1, count + 1)]


def movies(count=8):
    languages = ["Hindi", "Marathi", "English", "Telugu", "Tamil", "Malayalam", "Kannada", "Bengali"]
    return [{"id": i, "duration_minutes": 90 + i * 9, "language": languages[(i - 1) % len(languages)]}
            for i in range(1, count + 1)]


def test_deterministic_coverage_spacing_and_idempotence():
    result = generate_programme(screens(), movies(), DAY, ZONE)
    assert result == generate_programme(list(reversed(screens())), list(reversed(movies())), DAY, ZONE)
    counts = Counter(r["movie_id"] for r in result)
    assert set(counts) == set(range(1, 9)) and min(counts.values()) >= 2
    by_screen = defaultdict(list)
    for row in result:
        assert row["start_time"].time().replace(tzinfo=None) <= datetime.strptime("23:15", "%H:%M").time()
        assert row["start_time"].minute % 5 == 0
        by_screen[row["screen_id"]].append(row)
    for rows in by_screen.values():
        assert 9 <= rows[0]["start_time"].hour <= 10
        assert len({r["movie_id"] for r in rows}) <= 2
        for a, b in zip(rows, rows[1:]):
            assert b["start_time"] >= a["start_time"] + timedelta(minutes=a["duration_minutes"] + 20)
    assert generate_programme(screens(), movies(), DAY, ZONE, existing=result) == []


@pytest.mark.parametrize("chain,low,high,p_low,p_high", [("PVR INOX",220,320,380,520), ("Cinépolis",220,320,380,520),
    ("E-Square",180,260,280,380), ("City Pride",180,260,280,380), ("Miraj",180,260,280,380),
    ("Carnival",180,260,280,380), ("Independent",120,180,180,250)])
def test_base_prices_and_surcharges(chain, low, high, p_low, p_high):
    noon = datetime(2030, 1, 7, 12, tzinfo=ZONE)
    base = prices(chain, "2D", noon, 7)
    assert low <= base[0] <= high and p_low <= base[1] <= p_high
    for fmt in ("IMAX", "ICE", "4DX"):
        premium = prices(chain, fmt, noon + timedelta(days=4, hours=7), 7)
        for b, p in zip(base, premium):
            assert abs(float(p) - float(b) * 1.3 * 1.6) <= 5
            assert p % 10 == 0


def test_single_screen_local_films_and_existing_booking():
    local_movies = movies(3)
    screen = [{"id": i, "cinema_id": i, "chain": "Independent", "format": "2D", "screens_count": 1} for i in (1,2)]
    # Existing intervals are immutable inputs; their film also counts toward city coverage.
    existing = [{"screen_id": 1, "movie_id": 1, "duration_minutes": 99,
                 "start_time": datetime(2030, 1, 7, 15, tzinfo=ZONE)}]
    original = [dict(r) for r in existing]
    result = generate_programme(screen, local_movies[:2], DAY, ZONE, existing)
    assert existing == original
    all_rows = sorted(existing + [r for r in result if r["screen_id"] == 1], key=lambda r: r["start_time"])
    assert len({r["movie_id"] for r in all_rows}) <= 2
    for a,b in zip(all_rows, all_rows[1:]):
        assert b["start_time"] >= a["start_time"] + timedelta(minutes=a["duration_minutes"] + 20)


def test_today_only_future_and_explicit_capacity_error():
    now = datetime(2030, 1, 7, 22, 50, tzinfo=ZONE)
    result = generate_programme(screens(), movies(), DAY, ZONE, now=now)
    assert all(r["start_time"] > now for r in result)
    with pytest.raises(ValueError, match="capacity"):
        generate_programme(screens(1), movies(8), DAY, ZONE)


def test_recliner_prices_generated_only_for_screens_with_recliners():
    from app.pricing import recliner_price
    halls = screens()
    halls[0]["has_recliners"] = True
    result = generate_programme(halls,movies(),DAY,ZONE)
    for row in result:
        if row["screen_id"] == halls[0]["id"]:
            assert row["recliner_price"] == recliner_price(row["premium_price"])
            assert row["recliner_price"] % 10 == 0
        else:
            assert row["recliner_price"] is None
