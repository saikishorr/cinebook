"""Pure, deterministic training programmes. These are never real cinema showtimes."""
import hashlib
import random
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from app.pricing import recliner_price

LANGUAGE_WEIGHTS = {"Hindi": 30, "English": 22, "Marathi": 18, "Telugu": 10, "Tamil": 8,
                    "Malayalam": 5, "Kannada": 3}


def stable_seed(*parts):
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big")


def round_time(value):
    value = value.replace(second=0, microsecond=0) + (timedelta(minutes=1) if value.second or value.microsecond else timedelta())
    return value + timedelta(minutes=(-value.minute) % 5)


def prices(chain, screen_format, start, seed):
    rng = random.Random(seed)
    if chain in ("PVR INOX", "Cinépolis"):
        regular, premium = rng.randrange(220, 321, 10), rng.randrange(380, 521, 10)
    elif chain in ("E-Square", "City Pride", "Miraj", "Carnival"):
        regular, premium = rng.randrange(180, 261, 10), rng.randrange(280, 381, 10)
    else:
        regular, premium = rng.randrange(120, 181, 10), rng.randrange(180, 251, 10)
    # Each condition adds 15% of base price; the format multiplier follows that.
    factor = Decimal(1) + Decimal("0.15") * (int(start.weekday() >= 4) + int(start.hour >= 18))
    if screen_format in ("IMAX", "ICE", "4DX"):
        factor *= Decimal("1.60")
    return tuple((Decimal(p) * factor / 10).quantize(Decimal(1), rounding=ROUND_HALF_UP) * 10 for p in (regular, premium))


def week_start(day):
    """The Friday on or before this local calendar date."""
    return day - timedelta(days=(day.weekday() - 4) % 7)


def observed_plan(rows, zone, previous=None):
    """Recover the latest weekly pattern, excluding isolated protected exceptions.

    Latest dates take precedence over old times after a mid-week change. Earlier rows
    restore slots only when a protected exception blocks them on the reference date.
    """
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        local = row["start_time"].astimezone(zone)
        grouped[row["screen_id"]][local.date()].append({**row, "minute": local.hour * 60 + local.minute})
    result = {}
    for screen_id, dates in grouped.items():
        counts = Counter((r["minute"],r["movie_id"]) for values in dates.values() for r in values)
        prior = {(r["minute"], r["movie_id"]) for r in (previous or {}).get(screen_id, [])}
        last = max(dates)
        accepted = [r for r in dates[last] if not r.get("protected") or counts[(r["minute"],r["movie_id"])] >= 2
                    or (r["minute"], r["movie_id"]) in prior]
        blocked = [r for r in dates[last] if r not in accepted]
        for day in sorted(dates, reverse=True):
            if day == last:
                continue
            for row in dates[day]:
                start, end = row["minute"], row["minute"] + row["duration_minutes"] + 20
                if any(start < b["minute"] + b["duration_minutes"] + 20 and end > b["minute"] for b in blocked):
                    if not any(start < a["minute"] + a["duration_minutes"] + 20 and end > a["minute"] for a in accepted):
                        accepted.append(row)
        if accepted:
            result[screen_id] = [{"minute": r["minute"], "movie_id": r["movie_id"]}
                                 for r in sorted(accepted, key=lambda r: r["minute"])]
    return result


def _weights(movies, friday):
    languages = Counter(m["language"] for m in movies)
    other = sum(count for name, count in languages.items() if name not in LANGUAGE_WEIGHTS)
    values = {}
    for rank, movie in enumerate(movies):
        language = movie["language"]
        demand = LANGUAGE_WEIGHTS.get(language, 4) / (languages[language] if language in LANGUAGE_WEIGHTS else other)
        release = movie.get("release_date")
        age = max(0, (friday - release).days) if release else 90
        values[movie["id"]] = demand * (1 + max(0, 45 - age) / 45) / (1 + rank / max(1, len(movies)))
    return values


def _allocate(screen_list, lineup, anchor, priority):
    """Keep holdovers on their screens, then pair additions on the lower-ranked screens."""
    if not any(anchor.get(s["id"]) for s in screen_list):
        ranked = sorted(lineup, key=lambda film: priority[film])
        n = len(screen_list)
        if len(ranked) <= n:
            return {s["id"]: [ranked[i] if i < len(ranked) else ranked[0]] for i, s in enumerate(screen_list)}
        full = 2 * n - len(ranked)
        return {s["id"]: ([ranked[i]] if i < full else ranked[full + 2 * (i-full):full + 2 * (i-full) + 2])
                for i, s in enumerate(screen_list)}
    allocation = {}
    for screen in screen_list:
        films = list(dict.fromkeys(r["movie_id"] for r in anchor.get(screen["id"], []) if r["movie_id"] in lineup))
        allocation[screen["id"]] = sorted(films, key=lambda m: priority[m])[:2]
    for movie in sorted(lineup, key=lambda m: priority[m]):
        if any(movie in films for films in allocation.values()):
            continue
        # A departed partner leaves the most natural slot for a new release.
        eligible = [s for s in screen_list if len(allocation[s["id"]]) < 2]
        if not eligible:
            copies = Counter(m for films in allocation.values() for m in films)
            duplicate = next((s for s in reversed(screen_list) if any(copies[m] > 1 for m in allocation[s["id"]])), None)
            if duplicate is None:
                raise ValueError("Not enough screen capacity for weekly line-up")
            allocation[duplicate["id"]].remove(next(m for m in allocation[duplicate["id"]] if copies[m] > 1))
            eligible = [duplicate]
        screen = min(eligible, key=lambda s: (len(allocation[s["id"]]),
                    -max((priority[m] for m in allocation[s["id"]]), default=-1), s["id"]))
        allocation[screen["id"]].append(movie)
    top = min(lineup, key=lambda m: priority[m])
    for films in allocation.values():
        if not films:
            films.append(top)
    return allocation


def plan_week(screens, movies, friday, previous=None, current=None, forced=(), strict=True, commitments=None):
    """Choose weekly cinema line-ups citywide before allocating daily screen timetables."""
    if not screens or not movies:
        return {}
    movies = sorted(movies, key=lambda m: m["id"])
    by_id = {m["id"]: m for m in movies}
    priority = {m["id"]: rank for rank, m in enumerate(movies)}
    weights = _weights(movies, friday)
    groups = defaultdict(list)
    for screen in sorted(screens, key=lambda s: s["id"]):
        groups[screen["cinema_id"]].append(screen)
    anchors, lineups, limits, lounges = {}, {}, {}, {}
    for cinema_id, halls in sorted(groups.items()):
        lounges[cinema_id] = all(s.get("layout_name") == "lounge" for s in halls)
        limit = 2 if len(halls) == 1 else min(5, 2*len(halls)) if lounges[cinema_id] else max(3, len(halls)+2)
        limits[cinema_id] = min(len(movies), 2*len(halls), limit)
        allowed = {m["id"] for m in movies[:5]} if lounges[cinema_id] else set(by_id)
        for hall in halls:
            anchors[hall["id"]] = (current or {}).get(hall["id"]) or (previous or {}).get(hall["id"], [])
        carried = list(dict.fromkeys(r["movie_id"] for hall in halls for r in anchors[hall["id"]]
                                     if r["movie_id"] in allowed))
        committed = set((commitments or {}).get(cinema_id,())) & allowed
        lineups[cinema_id] = set(sorted(set(carried)|committed,
                                       key=lambda m: (m not in committed,priority[m]))[:limits[cinema_id]])

    def homes(movie):
        return {cinema for cinema, films in lineups.items() if movie in films}

    # Coverage is in cinemas, not seats or daily screening counts. Holdovers already count.
    for movie in sorted(by_id, key=lambda m: (m not in forced, priority[m])):
        while len(homes(movie)) < 2:
            choices = []
            for cinema, halls in sorted(groups.items()):
                if movie in lineups[cinema] or (lounges[cinema] and priority[movie] >= 5):
                    continue
                victim = None
                if len(lineups[cinema]) >= limits[cinema]:
                    donors = [m for m in lineups[cinema] if len(homes(m)) > 2 and m not in forced
                              and m not in (commitments or {}).get(cinema,())]
                    if not donors:
                        continue
                    # Prefer removing a lower-ranked shared film to a full-screen headliner.
                    shared = {r["movie_id"] for hall in halls if len({r["movie_id"] for r in anchors[hall["id"]]}) == 2
                              for r in anchors[hall["id"]]}
                    victim = max(donors, key=lambda m: (m in shared, priority[m]))
                foreign_single = len(halls) == 1 and by_id[movie]["language"] not in ("Hindi", "Marathi")
                score = (victim is not None, foreign_single, not lounges[cinema], len(lineups[cinema]) / limits[cinema],
                         stable_seed(cinema, friday, movie))
                choices.append((score, cinema, victim))
            if not choices:
                if strict:
                    raise ValueError("Not enough cinema capacity for two weekly homes for every active film")
                break
            _, cinema, victim = min(choices, key=lambda choice: choice[0])
            if victim is not None:
                lineups[cinema].remove(victim)
            lineups[cinema].add(movie)

    for cinema, halls in sorted(groups.items()):
        # A departed film's partner inherits its times. Filling that vacancy with a
        # random active film would undo deactivation and churn the established week.
        if any(anchors[hall["id"]] for hall in halls):
            continue
        rng = random.Random(stable_seed(cinema, friday))
        while len(lineups[cinema]) < limits[cinema]:
            candidates = [m for m in by_id if m not in lineups[cinema] and (not lounges[cinema] or priority[m] < 5)]
            if not candidates:
                break
            demand = [weights[m] * (8 if len(halls) == 1 and by_id[m]["language"] in ("Hindi", "Marathi") else 1)
                      for m in candidates]
            lineups[cinema].add(rng.choices(candidates, weights=demand)[0])

    plan = {}
    for cinema, halls in sorted(groups.items()):
        allocated = _allocate(halls, lineups[cinema], anchors, priority)
        for hall in halls:
            films = allocated[hall["id"]]
            old = anchors[hall["id"]]
            old_films = list(dict.fromkeys(r["movie_id"] for r in old))
            replacements = [m for m in films if m not in old_films]
            retained = [m for m in old_films if m in films]
            opening = old[0]["minute"] if old else 540 + 5*(stable_seed(cinema, friday, hall["id"]) % 19)
            slots = []
            if old and (len(films) == 1 or len(old_films) >= 2):
                departed = list(dict.fromkeys(r["movie_id"] for r in old if r["movie_id"] not in films))
                mapping = {m: replacements[min(i, len(replacements)-1)] if replacements else films[0]
                           for i, m in enumerate(departed)}
                for row in old:
                    movie = row["movie_id"] if row["movie_id"] in films else mapping[row["movie_id"]]
                    minute = max(row["minute"], slots[-1]["minute"] + 5*((by_id[slots[-1]["movie_id"]]["duration_minutes"]+24)//5)) if slots else row["minute"]
                    if minute <= 1395:
                        slots.append({"minute": minute, "movie_id": movie})
            else:
                # Fresh screen, or a previously full screen now alternating two films.
                minute, index = opening, 0
                order = retained + [m for m in films if m not in retained]
                while minute <= 1395:
                    movie = order[index % len(order)]
                    slots.append({"minute": minute, "movie_id": movie})
                    minute += 5*((by_id[movie]["duration_minutes"]+24)//5)
                    index += 1
            plan[hall["id"]] = slots
    return plan


def expand_plan(plan, screens, movies, day, zone, now=None):
    """Copy weekly clock slots onto this date. Only price seeds contain the date."""
    halls = {s["id"]: s for s in screens}
    films = {m["id"]: m for m in movies}
    rows = []
    for screen_id, slots in sorted(plan.items()):
        hall = halls[screen_id]
        for slot in slots:
            start = datetime.combine(day, time.min, zone) + timedelta(minutes=slot["minute"])
            if now and start <= now:
                continue
            regular, premium = prices(hall["chain"], hall["format"], start, stable_seed(screen_id, slot["minute"], day))
            rows.append({"screen_id": screen_id, "movie_id": slot["movie_id"], "start_time": start,
                         "duration_minutes": films[slot["movie_id"]]["duration_minutes"],
                         "regular_price": regular, "premium_price": premium,
                         "recliner_price": recliner_price(premium) if hall.get("has_recliners") else None})
    return rows


def generate_programme(screens, movies, day, zone, existing=(), now=None, fill=True, strict=True):
    """Compatibility entry point: one date materialized from a weekly citywide plan."""
    anchor = observed_plan(existing, zone)
    plan = plan_week(screens, movies, week_start(day), current=anchor, strict=strict)
    rows = expand_plan(plan, screens, movies, day, zone, now)
    return [r for r in rows if not any(r["screen_id"] == old["screen_id"]
            and r["start_time"] < old["start_time"] + timedelta(minutes=old["duration_minutes"]+20)
            and r["start_time"] + timedelta(minutes=r["duration_minutes"]+20) > old["start_time"] for old in existing)]


