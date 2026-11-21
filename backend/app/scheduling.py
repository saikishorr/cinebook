"""Persist generated demo programmes; shared by import scripts and the film admin."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from psycopg.rows import dict_row
from app.programme import expand_plan, observed_plan, plan_week, week_start
from collections import defaultdict


def clear_hidden_shows(connection, holds_backend="postgres", now=None):
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("""SELECT s.id FROM shows s JOIN movies m ON m.id = s.movie_id
                          JOIN screens sc ON sc.id = s.screen_id JOIN cinemas ci ON ci.id = sc.cinema_id
                          WHERE (NOT m.is_active OR NOT ci.is_active) AND s.start_time > COALESCE(%s::timestamptz,now())
                          AND NOT EXISTS (SELECT 1 FROM bookings b WHERE b.show_id = s.id)
                          AND NOT EXISTS (SELECT 1 FROM seat_holds h WHERE h.show_id = s.id AND h.expires_at > now())
                          FOR UPDATE OF s""",(now,))
        ids = [r["id"] for r in cursor.fetchall()]
        if holds_backend == "dynamodb" and ids:
            from app.holds import get_hold_store
            store = get_hold_store()
            # If AWS cannot be read we abort, rather than free a possibly held show.
            ids = [show_id for show_id in ids if not store.held_seat_ids(show_id)]
        cursor.execute("DELETE FROM seat_holds WHERE show_id = ANY(%s) AND expires_at <= now()", (ids,))
        cursor.execute("DELETE FROM shows WHERE id = ANY(%s)", (ids,))
        return cursor.rowcount


def _load_shows(cursor, start, end):
    cursor.execute("""SELECT s.id, s.screen_id, s.movie_id, s.start_time, m.duration_minutes,
                      (EXISTS (SELECT 1 FROM bookings b WHERE b.show_id=s.id)
                       OR EXISTS (SELECT 1 FROM seat_holds h WHERE h.show_id=s.id AND h.expires_at>now())) AS protected
                      FROM shows s JOIN screens sc ON sc.id=s.screen_id JOIN cinemas ci ON ci.id=sc.cinema_id
                      JOIN movies m ON m.id=s.movie_id WHERE ci.is_active AND s.status='SCHEDULED'
                      AND s.start_time >= %s AND s.start_time < %s FOR UPDATE OF s""", (start,end))
    return cursor.fetchall()


def _delete_shows(cursor, ids):
    cursor.execute("DELETE FROM seat_holds WHERE show_id=ANY(%s) AND expires_at<=now()", (ids,))
    cursor.execute("DELETE FROM shows WHERE id=ANY(%s)", (ids,))
    return cursor.rowcount


def schedule_shows(connection, days=8, now=None, app_timezone=None, holds_backend=None, movie_ids=None, rebuild=False):
    from app.config import settings
    zone = ZoneInfo(app_timezone or settings.app_timezone)
    backend = holds_backend or settings.holds_backend
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(zone).date()
    first_week = week_start(today)
    start = datetime.combine(first_week-timedelta(days=7),time.min,zone)
    end = datetime.combine(today+timedelta(days=days),time.min,zone)
    held_cache = {}

    def is_protected(row):
        if row["protected"]:
            return True
        if backend == "dynamodb" and row["start_time"] > now:
            from app.holds import get_hold_store
            if row["id"] not in held_cache:
                held_cache[row["id"]] = bool(get_hold_store().held_seat_ids(row["id"]))
            return held_cache[row["id"]]
        return False

    with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(641902109)")
        # Capture departed films' old slot patterns before cleanup, so partners inherit them.
        before = _load_shows(cursor,start,end)
        cleared = clear_hidden_shows(connection,backend,now=now)
        if rebuild:
            cursor.execute("""SELECT s.id, s.start_time,
                              (EXISTS (SELECT 1 FROM bookings b WHERE b.show_id=s.id)
                               OR EXISTS (SELECT 1 FROM seat_holds h WHERE h.show_id=s.id AND h.expires_at>now())) AS protected
                              FROM shows s JOIN screens sc ON sc.id=s.screen_id JOIN cinemas ci ON ci.id=sc.cinema_id
                              WHERE ci.is_active AND s.start_time>%s FOR UPDATE OF s""", (now,))
            cleared += _delete_shows(cursor,[r["id"] for r in cursor.fetchall() if not is_protected(r)])
        current = _load_shows(cursor,start,end)
        for row in current:
            row["protected"] = is_protected(row)
        cursor.execute("""SELECT sc.id, sc.cinema_id, sc.format, sc.layout_name, ci.chain,
                          EXISTS (SELECT 1 FROM seats st WHERE st.screen_id=sc.id AND st.seat_type='RECLINER') AS has_recliners,
                          count(*) OVER (PARTITION BY ci.id) AS screens_count
                          FROM screens sc JOIN cinemas ci ON ci.id=sc.cinema_id WHERE ci.is_active ORDER BY sc.id""")
        screens = cursor.fetchall()
        cursor.execute("SELECT id, language, duration_minutes, release_date FROM movies WHERE is_active ORDER BY id")
        movies = cursor.fetchall()
        weeks = sorted({week_start(today+timedelta(days=d)) for d in range(days)})
        previous = {} if rebuild else observed_plan(
            [r for r in before if week_start(r["start_time"].astimezone(zone).date()) == first_week-timedelta(days=7)],zone)
        plans = {}
        cinema_of = {s['id']:s['cinema_id'] for s in screens}
        for friday in weeks:
            # Later weeks inherit the just-planned week, including mid-week additions.
            # A previously generated Friday must not resurrect an older line-up.
            observed = {} if rebuild or friday > first_week else observed_plan(
                [r for r in before if week_start(r["start_time"].astimezone(zone).date()) == friday],zone,previous)
            if not rebuild and friday == first_week and today == friday+timedelta(days=6):
                # A first rebuild on Thursday afternoon stores only a partial Thursday.
                # Friday holds the complete copied plan; do not mistake missing morning
                # slots (or the old generator's past shows) for a new weekly timetable.
                complete = observed_plan([r for r in before if week_start(r["start_time"].astimezone(zone).date())
                                          == friday+timedelta(days=7)],zone,previous)
                observed.update(complete)
            commitments = defaultdict(set)
            for row in current:
                if row['protected'] and row['start_time']>now and week_start(row['start_time'].astimezone(zone).date())==friday:
                    commitments[cinema_of[row['screen_id']]].add(row['movie_id'])
            plan = plan_week(screens,movies,friday,previous=previous,current=observed,forced=movie_ids or (),commitments=commitments)
            plans[friday] = plan
            previous = plan
        desired = []
        for offset in range(days):
            day = today+timedelta(days=offset)
            desired.extend(expand_plan(plans[week_start(day)],screens,movies,day,zone,now))
        immutable = defaultdict(list)
        for row in current:
            if row["protected"] or row["start_time"] <= now:
                immutable[row["screen_id"]].append(row)
        allowed = []
        for row in desired:
            finish = row["start_time"] + timedelta(minutes=row["duration_minutes"]+20)
            collisions = [old for old in immutable[row["screen_id"]]
                          if row["start_time"] < old["start_time"]+timedelta(minutes=old["duration_minutes"]+20)
                          and finish > old["start_time"]]
            if any(old["start_time"] != row["start_time"] or old["movie_id"] != row["movie_id"] for old in collisions):
                continue
            allowed.append(row)
        keys = {(r["screen_id"],r["start_time"],r["movie_id"]) for r in allowed}
        obsolete = [r["id"] for r in current if r["start_time"]>now and not r["protected"]
                    and (r["screen_id"],r["start_time"],r["movie_id"]) not in keys]
        cleared += _delete_shows(cursor,obsolete)
        if allowed:
            cursor.executemany("""INSERT INTO shows (screen_id,movie_id,start_time,regular_price,premium_price,recliner_price)
                                  VALUES (%(screen_id)s,%(movie_id)s,%(start_time)s,%(regular_price)s,%(premium_price)s,%(recliner_price)s)
                                  ON CONFLICT (screen_id, start_time) DO NOTHING""",allowed)
            created = cursor.rowcount
        else:
            created = 0
    return {"created":created,"cleared":cleared}


