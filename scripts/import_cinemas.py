"""Import public OSM venue metadata. Seat maps are generated training data."""
import argparse
import hashlib
import json
import math
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))
SNAPSHOT = ROOT / "db/data/pune_cinemas.json"
CURATED = ROOT / "db/data/pune_cinemas_curated.json"
OVERRIDES = ROOT / "db/data/pune_cinemas_overrides.json"
BBOX = "18.40,73.70,18.75,74.05"
MIRRORS = ("https://overpass-api.de/api/interpreter", "https://lz4.overpass-api.de/api/interpreter",
           "https://overpass.private.coffee/api/interpreter")


def fetch(query, attempts=5):
    # Exhaust each mirror in order. Every attempt opens a fresh HTTPS connection.
    for mirror in MIRRORS:
        for attempt in range(attempts):
            request = urllib.request.Request(mirror, data=urllib.parse.urlencode({"data": query}).encode(),
                                             headers={"User-Agent": "CineBook-importer"})
            try:
                with urllib.request.urlopen(request, timeout=55) as response:
                    result = json.load(response)
                if "remark" in result:
                    raise ConnectionError("Overpass could not complete the query")
                # 'out tags' omits node coordinates. A second skeletal output supplies
                # geometry without requesting ways' full node lists or duplicating tags.
                merged = {}
                for element in result["elements"]:
                    key = (element["type"], element["id"])
                    merged[key] = {**merged.get(key, {}), **element}
                return list(merged.values())
            except urllib.error.HTTPError as error:
                if error.code not in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"Overpass returned HTTP {error.code}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError):
                pass
            print(f"Overpass mirror retry {attempt + 1}/{attempts}", flush=True)
            time.sleep(min(2 ** attempt, 12))
    raise RuntimeError("All Overpass mirrors failed. Retry later or use --offline with the committed snapshot.")


def folded(value):
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()


def chain_for(name, brand=""):
    text = folded(brand + " " + name)
    if "pvr" in text or "inox" in text:
        return "PVR INOX"
    if "cinepolis" in text:
        return "Cinépolis"
    if re.search(r"e[\s-]?square", text):
        return "E-Square"
    for chain in ("City Pride", "Miraj", "Carnival"):
        if chain.lower() in text:
            return chain
    return "Independent"


def distance(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def coordinates(element):
    point = element.get("center", element)
    return point["lat"], point["lon"]


def apply_overrides(cinemas, overrides):
    result = []
    for cinema in cinemas:
        key = cinema["osm_id"]
        if key in overrides.get("exclude", []):
            continue
        result.append({**cinema, "name": overrides.get("rename", {}).get(key, cinema["name"]),
                       "area": overrides.get("area", {}).get(key, cinema["area"])})
    return result


def clean_cinemas(elements, places, overrides=None):
    cinemas = []
    for element in elements:
        tags = element.get("tags", {})
        name = (tags.get("name:en") or tags.get("name") or tags.get("brand") or "Cinema").strip()
        lat, lon = coordinates(element)
        area = tags.get("addr:suburb") or tags.get("addr:city_district")
        if not area and places:
            nearest = min(places, key=lambda p: distance((lat, lon), coordinates(p)))
            area = nearest["tags"].get("name:en") or nearest["tags"].get("name")
        area = area or "Pune"
        chain = chain_for(name, tags.get("brand", ""))
        if folded(name) in ("pvr", "inox", "inox leisure", "pvr cinemas", "pvr inox", "cinepolis"):
            name = f"{chain} {area}"
        else:
            name = re.sub(r"\bcinemas\b", "Cinemas", name, flags=re.I)
        address = tags.get("addr:full") or ", ".join(dict.fromkeys(v for v in (
            tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:suburb"),
            tags.get("addr:city"), tags.get("addr:postcode")) if v)) or None
        count = re.search(r"\d+", tags.get("screen", tags.get("screens", "")))
        screens = int(count.group()) if count else {
            "PVR INOX": 6, "Cinépolis": 6, "E-Square": 5, "City Pride": 4, "Miraj": 4, "Carnival": 4,
        }.get(chain, 3 if "multiplex" in name.lower() else 1)
        cinemas.append({"osm_id": f"{element['type']}/{element['id']}", "name": name, "chain": chain,
                        "area": area, "address": address, "city": tags.get("addr:city", "Pune"),
                        "latitude": lat, "longitude": lon, "screens": max(1, min(screens, 30)),
                        "tags_count": len(tags)})
    cinemas = apply_overrides(cinemas, overrides or {})
    # Prefer richer OSM objects. Sorting also makes ties independent of API response order.
    kept = []
    for cinema in sorted(cinemas, key=lambda c: (-c["tags_count"], c["osm_id"])):
        if any(c["chain"] == cinema["chain"] and distance((c["latitude"], c["longitude"]),
               (cinema["latitude"], cinema["longitude"])) < 300 for c in kept):
            continue
        kept.append(cinema)
    return sorted(kept, key=lambda c: (c["name"].casefold(), c["osm_id"]))


def seat_layout(osm_id, screen_number, multiplex=True):
    digest = hashlib.sha256(f"{osm_id}:{screen_number}".encode()).digest()
    rows = 8 + digest[0] % 7 if multiplex else 16 + digest[0] % 5
    columns = 12 + digest[1] % 9 if multiplex else 22 + digest[1] % 7
    return rows, columns, 2 if multiplex else 4


def screen_formats(cinemas):
    # A public location or brand is not evidence of IMAX/ICE/4DX equipment.
    return {c["osm_id"]: next(f for f in c["formats"] if f != "2D") for c in cinemas
            if any(f != "2D" for f in c.get("formats", []))}


def load_snapshot(path=SNAPSHOT, overrides_path=OVERRIDES):
    if not path.exists():
        raise RuntimeError("Cinema snapshot is missing. Run scripts/import-cinemas.ps1 online once.")
    data = json.loads(path.read_text(encoding="utf-8"))
    overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
    return apply_overrides(data["cinemas"], overrides)


def import_cinemas(connection, cinemas):
    if not cinemas:
        raise ValueError("Refusing to replace the cinema catalogue with an empty list")
    formats = screen_formats(cinemas)
    created_screens = 0
    with connection.transaction(), connection.cursor() as cursor:
        cursor.executemany("""INSERT INTO cinemas (osm_id, name, chain, area, address, city, latitude, longitude)
                              VALUES (%(osm_id)s, %(name)s, %(chain)s, %(area)s, %(address)s, %(city)s, %(latitude)s, %(longitude)s)
                              ON CONFLICT (osm_id) DO UPDATE SET name = EXCLUDED.name, chain = EXCLUDED.chain,
                              area = EXCLUDED.area, address = EXCLUDED.address, city = EXCLUDED.city,
                              latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude, is_active = TRUE""", cinemas)
        cursor.execute("UPDATE cinemas SET is_active = FALSE WHERE osm_id IS NULL OR NOT (osm_id = ANY(%s))",
                       ([c["osm_id"] for c in cinemas],))
        cursor.execute("SELECT osm_id, id FROM cinemas WHERE osm_id = ANY(%s)", ([c["osm_id"] for c in cinemas],))
        ids = {row[0]: row[1] for row in cursor.fetchall()}
        for cinema in cinemas:
            for number in range(1, cinema["screens"] + 1):
                rows, columns, premium = seat_layout(cinema["osm_id"], number, cinema["screens"] > 1)
                format_name = formats.get(cinema["osm_id"], "2D") if number == 1 and cinema["screens"] > 1 else "2D"
                cursor.execute("""INSERT INTO screens (cinema_id, name, format, total_rows, seats_per_row)
                                  VALUES (%s, %s, %s, %s, %s) ON CONFLICT (cinema_id, name) DO NOTHING RETURNING id""",
                               (ids[cinema["osm_id"]], f"Audi {number}", format_name, rows, columns))
                screen = cursor.fetchone()
                if not screen:
                    continue
                created_screens += 1
                cursor.execute("""INSERT INTO seats (screen_id, row_label, seat_number, seat_type)
                                  SELECT %s, chr(64 + r), n, CASE WHEN r > %s THEN 'PREMIUM' ELSE 'REGULAR' END
                                  FROM generate_series(1, %s) r CROSS JOIN generate_series(1, %s) n""",
                               (screen[0], rows - premium, rows, columns))
    return created_screens


def load_curated(path=CURATED):
    cinemas = json.loads(Path(path).read_text(encoding="utf-8"))["cinemas"]
    if not cinemas or len({c["key"] for c in cinemas}) != len(cinemas):
        raise ValueError(f"{path}: curated cinema keys must be nonempty and unique")
    return cinemas


def _can_relayout(cursor, screen_id):
    # Lock show parents before checking: new bookings/holds cannot acquire a foreign-key
    # lock and slip in between this check and seat deletion.
    cursor.execute("SELECT id FROM shows WHERE screen_id = %s FOR UPDATE", (screen_id,))
    show_ids = [r["id"] for r in cursor.fetchall()]
    cursor.execute("SELECT 1 FROM bookings WHERE show_id = ANY(%s) LIMIT 1", (show_ids,))
    if cursor.fetchone():
        return False
    cursor.execute("SELECT 1 FROM seat_holds WHERE show_id = ANY(%s) AND expires_at > now() LIMIT 1", (show_ids,))
    if cursor.fetchone():
        return False
    cursor.execute("DELETE FROM seat_holds WHERE show_id = ANY(%s) AND expires_at <= now()", (show_ids,))
    return True


def import_curated(connection, cinemas, relayout=False, layout_root=None, schedule=True):
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
    from app.seat_layouts import LAYOUT_ROOT, build_seats, select_layout
    from app.scheduling import schedule_shows
    defaults = {"PVR INOX": 5, "Cinépolis": 6, "MovieMax": 4, "City Pride": 4,
                "Rajhans": 3, "Miraj": 3, "Mukta A2": 3, "Independent": 1}
    if not cinemas:
        raise ValueError("Refusing an empty curated cinema list")
    result = {"screens_created": 0, "screens_relaid": 0, "screens_skipped": 0}
    with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(641902109)")
        for cinema in cinemas:
            cursor.execute("""INSERT INTO cinemas (source_key, name, chain, area, address, latitude, longitude, location_precision)
                              VALUES (%(key)s, %(name)s, %(chain)s, %(area)s, %(address)s, %(latitude)s, %(longitude)s, %(location_precision)s)
                              ON CONFLICT (source_key) DO UPDATE SET name = EXCLUDED.name, chain = EXCLUDED.chain,
                              area = EXCLUDED.area, address = EXCLUDED.address, latitude = EXCLUDED.latitude,
                              longitude = EXCLUDED.longitude, location_precision = EXCLUDED.location_precision, is_active = TRUE
                              RETURNING id""", cinema)
            cinema_id = cursor.fetchone()["id"]
            lower_name = folded(cinema["name"])
            lounge = "director's cut" in lower_name or "moviemax gold" in lower_name
            count = 4 if lounge else cinema.get("screens") or defaults.get(cinema["chain"], 1)
            formats = [f for f in cinema.get("formats", []) if f != "2D"]
            for number in range(1, count + 1):
                vip = "cinepolis" in lower_name and "seasons" in lower_name and number == count
                name = "VIP" if vip else f"Audi {number}"
                template = "lounge" if lounge or vip else "single-screen" if cinema["chain"] == "Independent" and count == 1 else (
                    "multiplex-large" if number == 1 else "multiplex-medium" if number <= 3 else "multiplex-small")
                layout_name, layout = select_layout(cinema["key"], name, template, layout_root or LAYOUT_ROOT)
                width = len(layout["rows"][0].split(maxsplit=1)[1])
                format_name = formats[number - 1] if number <= len(formats) else "2D"
                cursor.execute("""INSERT INTO screens (cinema_id, name, format, total_rows, seats_per_row, layout_name, section_names)
                                  VALUES (%s, %s, %s, %s, %s, %s, %s)
                                  ON CONFLICT (cinema_id, name) DO NOTHING RETURNING id""",
                               (cinema_id, name, format_name, len(layout["rows"]), width, layout_name, Jsonb(layout["section_names"])))
                screen = cursor.fetchone()
                created = screen is not None
                if not created:
                    cursor.execute("SELECT id FROM screens WHERE cinema_id = %s AND name = %s FOR UPDATE", (cinema_id, name))
                    screen = cursor.fetchone()
                    if not relayout:
                        continue
                    if not _can_relayout(cursor, screen["id"]):
                        result["screens_skipped"] += 1
                        continue
                    cursor.execute("DELETE FROM seats WHERE screen_id = %s", (screen["id"],))
                    cursor.execute("""UPDATE screens SET format = %s, total_rows = %s, seats_per_row = %s, layout_name = %s,
                                      section_names = %s WHERE id = %s""",
                                   (format_name, len(layout["rows"]), width, layout_name, Jsonb(layout["section_names"]), screen["id"]))
                seats = [{**seat, "screen_id": screen["id"]} for seat in build_seats(layout)]
                cursor.executemany("""INSERT INTO seats (screen_id, row_label, seat_number, seat_type, row_index, col, accessible)
                                      VALUES (%(screen_id)s, %(row_label)s, %(seat_number)s, %(seat_type)s, %(row_index)s, %(col)s, %(accessible)s)""", seats)
                result["screens_created" if created else "screens_relaid"] += 1
                cursor.execute("""UPDATE shows SET recliner_price = CASE WHEN %s THEN round(premium_price * 1.8 / 10) * 10 ELSE NULL END
                                  WHERE screen_id = %s AND start_time > now()""",
                               (any(s["seat_type"] == "RECLINER" for s in seats), screen["id"]))
        cursor.execute("UPDATE cinemas SET is_active = FALSE WHERE source_key IS NULL OR NOT (source_key = ANY(%s))",
                       ([c["key"] for c in cinemas],))
        if schedule:
            result.update(schedule_shows(connection))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", choices=["curated", "osm"], default="curated")
    parser.add_argument("--relayout", action="store_true")
    args = parser.parse_args()
    if args.source == "curated":
        cinemas = load_curated()
    elif args.offline:
        cinemas = load_snapshot()
    else:
        elements = fetch(f'[out:json][timeout:40];nwr["amenity"="cinema"]({BBOX});out center tags;out skel center;')
        places = fetch(f'[out:json][timeout:40];node["place"~"suburb|neighbourhood|quarter"]({BBOX});out body;')
        overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
        cinemas = clean_cinemas(elements, places, overrides)
        if not cinemas:
            raise SystemExit("OSM returned no cinemas; the existing snapshot was kept.")
        SNAPSHOT.write_text(json.dumps({"source": "OpenStreetMap contributors (ODbL)",
            "source_url": "https://www.openstreetmap.org/copyright", "bbox": BBOX,
            "fetched_at": datetime.now(timezone.utc).isoformat(), "cinemas": cinemas}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.dry_run:
        print(f"{len(cinemas)} cinemas; database unchanged")
        return
    import psycopg
    from dotenv import dotenv_values
    from setup_local import apply_migrations
    values = dotenv_values(ROOT / "backend/.env")
    with psycopg.connect(values["DATABASE_URL"], autocommit=True) as connection:
        apply_migrations(connection)
        if args.source == "curated":
            result = import_curated(connection, cinemas, relayout=args.relayout)
        else:
            screens = import_cinemas(connection, cinemas)
            from app.scheduling import schedule_shows
            result = {"screens_created": screens, **schedule_shows(connection)}
    print(f"Imported {len(cinemas)} real {args.source} cinemas; {result}. DEMO tickets only.")


if __name__ == "__main__":
    main()
