"""Import the movies now playing in Pune cinemas into CineBook, with details from TMDB (The Movie Database).

By default the film list comes from db/data/pune_now_showing.json, a hand-kept list of what Pune
cinemas are screening this week (no free feed lists films by city). TMDB supplies the poster,
runtime, genres and trailer. --source india uses TMDB's all-India now-playing list instead (the
older behaviour described below).

    .venv\\Scripts\\python scripts\\import_tmdb.py            # import and reschedule shows
    .venv\\Scripts\\python scripts\\import_tmdb.py --dry-run  # only list what would be imported

TMDB lists releases by country, not by city, so "Pune" means: every film now playing in India, in
every language (Marathi, Hindi, English, Telugu, Tamil, Malayalam, Kannada, Punjabi, Bengali,
Gujarati and foreign releases), as Pune multiplexes screen them all. A few Marathi films and the top
films of each South Indian language are guaranteed a place, and the rest are ranked by popularity.

What it does:
  1. Reads TMDB_API_KEY from backend/.env. Both the short "API Key" and the long
     "API Read Access Token" from https://www.themoviedb.org/settings/api work.
  2. Fetches India's "now playing" list plus each Indian language's recent releases, then each film's runtime,
     genres, Indian (CBFC) certificate and YouTube trailer.
  3. Upserts the films into `movies` (matched on tmdb_id) and hides every other movie,
     including the three sample films. Hidden movies keep their bookings.
  4. Deletes future shows of hidden movies that nobody has booked or is holding, then runs
     db/add_upcoming_shows.sql to fill the free slots with the new films.

Run it again each week (new releases come in on Fridays) to keep the listings current.
Required attribution: "This product uses the TMDB API but is not endorsed or certified by TMDB."
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))
from app.tmdb import Tmdb, details, certificate, trailer, DEFAULT_RUNTIME  # noqa: E402, F401

# Indian languages whose recent theatrical releases are fetched individually, so regional films
# that are not nationally popular still make the list.
INDIAN_LANGUAGES = ["mr", "hi", "te", "ta", "ml", "kn", "pa", "bn", "gu"]
# Guaranteed places per language (Marathi is Pune's local language; Pune has large Telugu, Tamil,
# Malayalam and Kannada audiences). Everything else competes on popularity.
GUARANTEED = {"mr": 4, "hi": 4, "en": 4, "te": 3, "ta": 3, "ml": 2, "kn": 2}
RECENT_DAYS = 35         # how far back a "recent release" goes for the per-language lists


def candidates(tmdb: Tmdb, pages: int) -> list[dict]:
    """India's now-playing list plus Marathi films released in the last six weeks, without duplicates."""
    found: dict[int, dict] = {}
    for page in range(1, pages + 1):
        data = tmdb.get("/movie/now_playing", region="IN", language="en-IN", page=page)
        for movie in data.get("results", []):
            found.setdefault(movie["id"], movie)
        if page >= data.get("total_pages", 1):
            break
    today = date.today()
    for code in INDIAN_LANGUAGES:
        # Theatrical releases (types 2 and 3) in India in the last few weeks, most popular first.
        recent = tmdb.get("/discover/movie", region="IN", language="en-IN", with_original_language=code,
                          with_release_type="2|3", sort_by="popularity.desc",
                          **{"release_date.gte": (today - timedelta(days=RECENT_DAYS)).isoformat(),
                             "release_date.lte": today.isoformat()})
        for movie in recent.get("results", []):
            found.setdefault(movie["id"], movie)
    return list(found.values())


def choose(movies: list[dict], limit: int) -> list[dict]:
    """The guaranteed places per language first, then every other film by popularity, up to `limit`."""
    usable = [m for m in movies if m.get("poster_path") and not m.get("adult")]
    by_popularity = sorted(usable, key=lambda m: -(m.get("popularity") or 0))
    picked: list[dict] = []
    for code, places in GUARANTEED.items():
        picked += [m for m in by_popularity if m.get("original_language") == code][:places]
    picked += [m for m in by_popularity if m not in picked]
    # Show them most popular first; the guarantee only decides who is in, not the order.
    return sorted(picked[:limit], key=lambda m: -(m.get("popularity") or 0))


# ---------------------------------------------------------------- Pune list (default source)
PUNE_LIST = ROOT / "db/data/pune_now_showing.json"


def cbfc(value: str) -> str:
    """Pune listings show CBFC's current ratings (U, UA7+, UA13+, UA16+, A); the database stores U / UA / A."""
    value = (value or "").upper().replace(" ", "").replace("/", "")
    if value.startswith("UA"):
        return "UA"
    return value if value in ("U", "A") else "UA"


def _norm(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


def find_on_tmdb(tmdb: Tmdb, film: dict) -> dict | None:
    """The TMDB film behind a Pune listing: pinned id, else an exact-title match, else the most popular recent hit."""
    if film.get("tmdb") is False:                              # known mismatch: list it without TMDB details
        return None
    if film.get("tmdb_id"):
        return {"id": film["tmdb_id"]}
    query = film.get("tmdb_query") or film["title"]
    params = {"query": query, "language": "en-IN", "include_adult": "false"}
    if film.get("year"):
        params["primary_release_year"] = film["year"]
    results = tmdb.get("/search/movie", **params).get("results", [])
    if not results and film.get("year"):                       # Indian release year can differ from TMDB's
        params.pop("primary_release_year")
        results = tmdb.get("/search/movie", **params).get("results", [])
    recent = [r for r in results if (r.get("release_date") or "9999") >= (date.today() - timedelta(days=540)).isoformat()]
    pool = recent or results
    wanted = {_norm(film["title"]), _norm(query)}
    exact = [r for r in pool if _norm(r.get("title")) in wanted or _norm(r.get("original_title")) in wanted]
    ranked = sorted(exact or pool, key=lambda r: -(r.get("popularity") or 0))
    return ranked[0] if ranked else None


def pune_films(tmdb: Tmdb) -> list[dict]:
    listing = json.loads(PUNE_LIST.read_text(encoding="utf-8"))
    print(f"Pune list researched on {listing.get('researched_on', '?')}: {len(listing['films'])} films")
    films = []
    seen: dict[int, str] = {}
    for entry in listing["films"]:
        match = find_on_tmdb(tmdb, entry)
        if match and match["id"] in seen:
            # Two listings for one film (usually a dubbed version under another title): keep the first.
            print(f"  ! '{entry['title']}' is the same TMDB film as '{seen[match['id']]}'; skipped. "
                  "Remove one of them from the list, or pin the right one with tmdb_id.")
            continue
        if match:
            seen[match["id"]] = entry["title"]
        if match:
            film = details(tmdb, match)
            film["title"] = entry["title"]                     # the name Pune cinemas use
        else:
            # Not on TMDB yet (common for small regional releases): list it anyway, without a poster.
            film = {"tmdb_id": None, "title": entry["title"], "description": None,
                    "duration_minutes": entry.get("duration_minutes") or DEFAULT_RUNTIME,
                    "poster_url": None, "backdrop_url": None, "trailer_url": None, "genres": [],
                    "release_date": None}
        film["language"] = entry["language"]                   # the language it plays in Pune (may be dubbed)
        film["certificate"] = cbfc(entry.get("certificate"))
        film["_matched"] = bool(match)
        films.append(film)
    return films


UPSERT = """
INSERT INTO movies (tmdb_id, title, description, duration_minutes, language, certificate,
                    poster_url, backdrop_url, trailer_url, genres, release_date, is_active)
VALUES (%(tmdb_id)s, %(title)s, %(description)s, %(duration_minutes)s, %(language)s, %(certificate)s,
        %(poster_url)s, %(backdrop_url)s, %(trailer_url)s, %(genres)s, %(release_date)s, TRUE)
ON CONFLICT (tmdb_id) DO UPDATE SET
    title = EXCLUDED.title, description = EXCLUDED.description, duration_minutes = EXCLUDED.duration_minutes,
    language = EXCLUDED.language, certificate = EXCLUDED.certificate, poster_url = EXCLUDED.poster_url,
    backdrop_url = EXCLUDED.backdrop_url, trailer_url = EXCLUDED.trailer_url, genres = EXCLUDED.genres,
    release_date = EXCLUDED.release_date, is_active = TRUE
"""

# Free the coming slots held by hidden movies, but never touch a show someone has booked or is holding.
CLEAR_HIDDEN_SHOWS = """
DELETE FROM shows AS s
USING movies AS m
WHERE m.id = s.movie_id AND NOT m.is_active AND s.start_time > now()
  AND NOT EXISTS (SELECT 1 FROM bookings AS b WHERE b.show_id = s.id)
  AND NOT EXISTS (SELECT 1 FROM seat_holds AS h WHERE h.show_id = s.id)
"""


def save(database_url: str, films: list[dict]) -> None:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.transaction():
        has_column = connection.execute("""SELECT 1 FROM information_schema.columns
                                        WHERE table_name = 'movies' AND column_name = 'tmdb_id'""").fetchone()
        if not has_column:
            raise SystemExit("The movies table has no tmdb_id column yet. Run .\\scripts\\setup-local.ps1 first.")
        keep_ids = []
        for film in films:
            values = {k: v for k, v in film.items() if not k.startswith("_")}
            if values["tmdb_id"] is not None:
                connection.execute(UPSERT, values)
                keep_ids.append(connection.execute("SELECT id FROM movies WHERE tmdb_id = %s",
                                                   (values["tmdb_id"],)).fetchone()[0])
                continue
            # A film TMDB does not know yet is matched on its title instead.
            row = connection.execute("SELECT id FROM movies WHERE tmdb_id IS NULL AND lower(title) = lower(%s)",
                                     (values["title"],)).fetchone()
            if row:
                connection.execute("""UPDATE movies SET language = %(language)s, certificate = %(certificate)s,
                                      is_active = TRUE WHERE id = %(id)s""", {**values, "id": row[0]})
                keep_ids.append(row[0])
            else:
                keep_ids.append(connection.execute(
                    """INSERT INTO movies (title, description, duration_minutes, language, certificate, genres, is_active)
                       VALUES (%(title)s, %(description)s, %(duration_minutes)s, %(language)s, %(certificate)s,
                               %(genres)s, TRUE) RETURNING id""", values).fetchone()[0])
        hidden = connection.execute("""UPDATE movies SET is_active = FALSE
                                       WHERE is_active AND NOT (id = ANY(%s))""", (keep_ids,)).rowcount
        from schedule_shows import schedule_shows
        scheduled = schedule_shows(connection)
        cleared = scheduled['cleared']
        upcoming = connection.execute("""SELECT count(*) FROM shows AS s JOIN movies AS m ON m.id = s.movie_id
                                         WHERE m.is_active AND s.start_time > now() AND s.status = 'SCHEDULED'""").fetchone()[0]
    print(f"\nSaved {len(films)} movies, hid {hidden} older ones, freed {cleared} unbooked shows, "
          f"created {scheduled['created']} demo shows; {upcoming} upcoming shows now scheduled for the new films.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import movies now playing in Pune from TMDB.")
    parser.add_argument("--limit", type=int, default=40, help="how many movies to list (default 40)")
    parser.add_argument("--pages", type=int, default=5, help="now-playing pages to scan, 20 films each (default 3)")
    parser.add_argument("--source", choices=["pune", "india"], default="pune",
                        help="pune: the hand-kept Pune list in db/data/pune_now_showing.json (default); "
                             "india: TMDB's all-India now-playing list")
    parser.add_argument("--dry-run", action="store_true", help="print the selection without changing the database")
    args = parser.parse_args()

    from dotenv import dotenv_values
    env = dotenv_values(ROOT / "backend/.env")
    key = env.get("TMDB_API_KEY") or ""
    if not key.strip() or key.strip() == "CHANGE_ME":
        raise SystemExit("Add TMDB_API_KEY to backend/.env (free key: https://www.themoviedb.org/settings/api).")

    tmdb = Tmdb(key)
    if args.source == "pune":
        films = pune_films(tmdb)
    else:
        films = [details(tmdb, movie) for movie in choose(candidates(tmdb, args.pages), args.limit)]
    if not films:
        raise SystemExit("TMDB returned no suitable films for India right now; nothing was changed.")
    for film in films:
        flag = "" if film.get("_matched", True) else "   (not on TMDB: no poster)"
        print(f"  {film['title'][:40]:40} {film['language']:9} {film['certificate']:3} "
              f"{film['duration_minutes']:>3} min  released {film['release_date'] or '?'}{flag}")
    if args.dry_run:
        print("\nDry run: the database was not changed.")
        return
    save(env["DATABASE_URL"], films)


if __name__ == "__main__":
    sys.exit(main())
