"""Six cinemas and twelve films: weekly continuity, holdovers and protected intervals."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from psycopg.rows import dict_row, tuple_row

from app.programme import expand_plan, plan_week, week_start
from app.scheduling import schedule_shows
from tests.test_migrations import isolated_schema as isolated_schema, ROOT

ZONE = ZoneInfo("Asia/Kolkata")
FRIDAY = date(2030,1,4)


def fixture_data():
    screens = []
    for cinema, count in enumerate((4,4,3,3,1,4),start=1):
        for number in range(count):
            screens.append({"id":len(screens)+1,"cinema_id":cinema,"chain":"Independent" if count==1 else "PVR INOX",
                            "format":"2D","layout_name":"lounge" if cinema==6 else "multiplex-medium",
                            "screens_count":count,"has_recliners":True})
    languages = ["Hindi","Marathi","English","Telugu","Tamil","Malayalam","Kannada","Bengali"]
    movies = [{"id":i+1,"language":languages[i%8],"duration_minutes":100+5*(i%8),
               "release_date":FRIDAY-timedelta(days=i*2)} for i in range(12)]
    return screens,movies


def homes(plan,screens):
    cinema = {s["id"]:s["cinema_id"] for s in screens}
    result = defaultdict(set)
    for screen,slots in plan.items():
        for slot in slots:
            result[slot["movie_id"]].add(cinema[screen])
    return result


@pytest.mark.parametrize("offset,expected",[(0,0),(1,0),(3,0),(6,0),(7,7),(10,7)])
def test_week_starts_on_friday(offset,expected):
    assert week_start(FRIDAY+timedelta(days=offset)) == FRIDAY+timedelta(days=expected)


def test_weekly_fixed_times_coverage_determinism_and_holdovers():
    screens,movies = fixture_data()
    first = plan_week(screens,movies,FRIDAY)
    assert first == plan_week(list(reversed(screens)),list(reversed(movies)),FRIDAY)
    assert set(homes(first,screens)) == {m["id"] for m in movies}
    assert min(map(len,homes(first,screens).values())) >= 2
    daily = []
    for offset in range(7):
        rows = expand_plan(first,screens,movies,FRIDAY+timedelta(days=offset),ZONE)
        daily.append({(r["screen_id"],r["movie_id"],r["start_time"].time()) for r in rows})
        by_screen = defaultdict(list)
        for row in rows:
            assert row["start_time"].time() <= time(23,15)
            by_screen[row["screen_id"]].append(row)
        for values in by_screen.values():
            assert len({r["movie_id"] for r in values}) <= 2
            for a,b in zip(values,values[1:]):
                assert b["start_time"] >= a["start_time"]+timedelta(minutes=a["duration_minutes"]+20)
    assert all(value == daily[0] for value in daily)
    second = plan_week(screens,movies,FRIDAY+timedelta(days=7),previous=first)
    before,after = homes(first,screens),homes(second,screens)
    for cinema in range(1,7):
        old = {film for film,venues in before.items() if cinema in venues}
        new = {film for film,venues in after.items() if cinema in venues}
        assert len(old&new)/len(old) >= .7
    for screen,slots in first.items():
        assert second[screen] == slots
    # The all-recliner cinema only carries top-ranked films.
    assert all(film <= 5 for film,venues in before.items() if 6 in venues)


@pytest.fixture
def weekly_db(isolated_schema):
    conn = isolated_schema
    conn.row_factory = dict_row
    conn.execute((ROOT/'db/schema.sql').read_text())
    screens,movies = fixture_data()
    actual_screens = []
    for cinema in range(1,7):
        cid = conn.execute("INSERT INTO cinemas (name,chain,area,latitude,longitude) VALUES (%s,'PVR INOX','Pune',18.5,73.8) RETURNING id", (f"Cinema {cinema}",)).fetchone()["id"]
        for hall in [s for s in screens if s["cinema_id"]==cinema]:
            sid = conn.execute("INSERT INTO screens (cinema_id,name,total_rows,seats_per_row,layout_name) VALUES (%s,%s,2,4,%s) RETURNING id", (cid,f"Audi {hall['id']}",hall['layout_name'])).fetchone()["id"]
            conn.execute("INSERT INTO seats (screen_id,row_label,seat_number,seat_type) VALUES (%s,'A',1,'REGULAR')", (sid,))
            actual_screens.append({**hall,"id":sid,"cinema_id":cid})
    for movie in movies:
        conn.execute("INSERT INTO movies (title,language,duration_minutes,certificate,release_date) VALUES (%s,%s,%s,'U',%s)",
                     (f"Film {movie['id']}",movie['language'],movie['duration_minutes'],movie['release_date']))
    try:
        yield conn,actual_screens
    finally:
        conn.row_factory = tuple_row


def rows(conn):
    return conn.execute("""SELECT s.*,sc.cinema_id,m.duration_minutes FROM shows s
                           JOIN screens sc ON sc.id=s.screen_id JOIN movies m ON m.id=s.movie_id
                           ORDER BY s.start_time,s.screen_id""").fetchall()


def assert_continuity(data,now,end):
    pairs = defaultdict(set)
    times = defaultdict(set)
    for row in data:
        local = row["start_time"].astimezone(ZONE)
        if row["start_time"] <= now or local.date() >= end:
            continue
        pairs[(row["cinema_id"],row["movie_id"],week_start(local.date()))].add(local.date())
        times[(row["screen_id"],week_start(local.date()),local.date())].add((local.time(),row["movie_id"]))
    failures = []
    for (cinema,film,week),days in pairs.items():
        start = min(days)
        expected = {start+timedelta(days=i) for i in range((min(week+timedelta(days=7),end)-start).days)}
        if days != expected:
            failures.append((cinema,film,sorted(expected-days)))
    assert failures == [], f"Unexpected continuity gaps (protected exceptions must be explicit): {failures}"
    for (screen,week,day),slots in times.items():
        if day == now.astimezone(ZONE).date():
            continue
        for (other_screen,other_week,other_day),other_slots in times.items():
            if other_screen==screen and other_week==week and other_day != now.astimezone(ZONE).date():
                assert slots == other_slots


def test_persisted_two_weeks_every_day_coverage_and_idempotence(weekly_db):
    conn,screens = weekly_db
    now = datetime.combine(FRIDAY,time(8),ZONE)
    result = schedule_shows(conn,now=now,rebuild=True)
    assert result['created'] > 500
    data = rows(conn)
    assert_continuity(data,now,FRIDAY+timedelta(days=8))
    for offset in range(8):
        day = FRIDAY+timedelta(days=offset)
        for movie in range(1,13):
            venues = {r['cinema_id'] for r in data if r['movie_id']==movie and r['start_time'].astimezone(ZONE).date()==day}
            assert len(venues) >= 2
    assert schedule_shows(conn,now=now) == {'created':0,'cleared':0}


def test_midweek_activation_fixed_patterns_then_holdover(weekly_db):
    conn,screens = weekly_db
    initial = datetime.combine(FRIDAY,time(8),ZONE)
    schedule_shows(conn,now=initial,rebuild=True)
    original = rows(conn)[0]
    customer = conn.execute("INSERT INTO customers (full_name,email) VALUES ('Protected','protected@example.com') RETURNING id").fetchone()['id']
    conn.execute("INSERT INTO bookings (booking_ref,customer_id,show_id,total_amount) VALUES ('PROTECTED',%s,%s,200)", (customer,original['id']))
    new = conn.execute("INSERT INTO movies (title,language,certificate,duration_minutes,release_date) VALUES ('New release','Hindi','U',130,%s) RETURNING id", (FRIDAY+timedelta(days=4),)).fetchone()['id']
    tuesday = datetime.combine(FRIDAY+timedelta(days=4),time(8),ZONE)
    schedule_shows(conn,now=tuesday,movie_ids=[new])
    data = rows(conn)
    assert next(r for r in data if r['id']==original['id']) == original
    carried = defaultdict(dict)
    for row in data:
        if row['movie_id']==new:
            carried[row['cinema_id']].setdefault(row['start_time'].astimezone(ZONE).date(),set()).add(row['start_time'].astimezone(ZONE).time())
    assert len(carried) >= 2
    for cinema,dates in carried.items():
        for offset in range(4,7):
            assert FRIDAY+timedelta(days=offset) in dates
        assert dates[FRIDAY+timedelta(days=4)] == dates[FRIDAY+timedelta(days=5)] == dates[FRIDAY+timedelta(days=6)]
        assert FRIDAY+timedelta(days=7) in dates
    assert schedule_shows(conn,now=tuesday) == {'created':0,'cleared':0}


def test_rebuild_retains_booking_and_live_hold_and_lists_blocked_slots(weekly_db):
    conn,screens = weekly_db
    now = datetime.combine(FRIDAY,time(8),ZONE)
    schedule_shows(conn,now=now,rebuild=True)
    old = rows(conn)
    held = old[1]
    seat = conn.execute("SELECT id FROM seats WHERE screen_id=%s", (held['screen_id'],)).fetchone()['id']
    conn.execute("INSERT INTO seat_holds (hold_id,show_id,seat_ids,expires_at) VALUES ('weekly-hold',%s,%s,now()+interval '1 hour')", (held['id'],[seat]))
    customer = conn.execute("INSERT INTO customers (full_name,email) VALUES ('Test','weekly@example.com') RETURNING id").fetchone()['id']
    booked = old[0]
    conn.execute("INSERT INTO bookings (booking_ref,customer_id,show_id,total_amount) VALUES ('WEEKLY',%s,%s,200)", (customer,booked['id']))
    result = schedule_shows(conn,now=now,rebuild=True)
    assert result['cleared'] == len(old)-2
    assert next(r for r in rows(conn) if r['id']==held['id']) == held
    assert next(r for r in rows(conn) if r['id']==booked['id']) == booked
    assert schedule_shows(conn,now=now) == {'created':0,'cleared':0}


def test_thursday_rebuild_does_not_relearn_old_morning_shows(weekly_db):
    conn,screens = weekly_db
    thursday = FRIDAY+timedelta(days=6)
    conn.execute("INSERT INTO shows (screen_id,movie_id,start_time,regular_price,premium_price) VALUES (%s,12,%s,200,300)",
                 (screens[0]['id'],datetime.combine(thursday,time(8),ZONE)))
    now = datetime.combine(thursday,time(12),ZONE)
    schedule_shows(conn,now=now,rebuild=True)
    assert schedule_shows(conn,now=now) == {'created':0,'cleared':0}


def test_off_plan_protected_show_blocks_only_its_intervals(weekly_db):
    conn,screens = weekly_db
    now = datetime.combine(FRIDAY,time(8),ZONE)
    schedule_shows(conn,now=now,rebuild=True)
    baseline = rows(conn)
    hall = screens[0]
    lineup = {r['movie_id'] for r in baseline if r['cinema_id']==hall['cinema_id']}
    film = next(i for i in range(1,13) if i not in lineup)
    reference = next(r for r in baseline if r['screen_id']==hall['id'] and r['start_time'].astimezone(ZONE).date()==FRIDAY+timedelta(days=6))
    extra = conn.execute("INSERT INTO shows (screen_id,movie_id,start_time,regular_price,premium_price) VALUES (%s,%s,%s,190,290) RETURNING *",
                         (hall['id'],film,reference['start_time']+timedelta(minutes=5))).fetchone()
    duration = conn.execute("SELECT duration_minutes FROM movies WHERE id=%s", (film,)).fetchone()['duration_minutes']
    customer = conn.execute("INSERT INTO customers (full_name,email) VALUES ('Exception','exception@example.com') RETURNING id").fetchone()['id']
    conn.execute("INSERT INTO bookings (booking_ref,customer_id,show_id,total_amount) VALUES ('EXCEPTION',%s,%s,190)", (customer,extra['id']))
    blocked = [(r['screen_id'],r['start_time']) for r in baseline if r['screen_id']==hall['id']
               and r['start_time'] < extra['start_time']+timedelta(minutes=duration+20)
               and r['start_time']+timedelta(minutes=r['duration_minutes']+20)>extra['start_time']]
    assert blocked, f'Expected explicit protected exceptions for show {extra["id"]}'
    schedule_shows(conn,now=now,rebuild=True)
    remaining = {(r['screen_id'],r['start_time']) for r in rows(conn)}
    assert all(slot not in remaining for slot in blocked), f'Protected blocked slots: {blocked}'
    assert conn.execute("SELECT * FROM shows WHERE id=%s", (extra['id'],)).fetchone() == extra
    assert schedule_shows(conn,now=now) == {'created':0,'cleared':0}


def test_deactivated_shared_film_slots_go_to_partner(weekly_db):
    conn,screens = weekly_db
    now = datetime.combine(FRIDAY,time(8),ZONE)
    schedule_shows(conn,now=now,rebuild=True)
    baseline = rows(conn)
    by_screen = defaultdict(set)
    for row in baseline:
        by_screen[row['screen_id']].add(row['movie_id'])
    hall,films = next((screen,films) for screen,films in by_screen.items() if len(films)==2)
    departed = max(films)
    partner = min(films)
    old_slots = {r['start_time'].time() for r in baseline if r['screen_id']==hall and r['movie_id']==departed}
    conn.execute("UPDATE movies SET is_active=FALSE WHERE id=%s", (departed,))
    tuesday = datetime.combine(FRIDAY+timedelta(days=4),time(8),ZONE)
    schedule_shows(conn,now=tuesday)
    after = rows(conn)
    assert not any(r['movie_id']==departed and r['start_time']>tuesday for r in after)
    # The shorter partner can keep the old alternating times, rather than leaving empty slots.
    assert old_slots <= {r['start_time'].time() for r in after if r['screen_id']==hall and r['movie_id']==partner and r['start_time']>tuesday}
    assert schedule_shows(conn,now=tuesday) == {'created':0,'cleared':0}
