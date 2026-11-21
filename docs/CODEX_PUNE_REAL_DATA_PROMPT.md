# CineBook: real Pune cinemas, realistic seat layouts and a film admin (backend work for Codex)

This is the third backend round. The hard rules in `docs/CODEX_BACKEND_PROMPT.md` still apply. In short:
- Do not touch `frontend/`.
- API changes are additive only, and the cloud defaults must keep working.
- Use plain psycopg SQL and numbered migrations with `_down.sql` files, also appended to `db/schema.sql`.
- Scripts must work in PowerShell 5.1; no new dependencies (stdlib only for hashing).
- Tests must pass offline.

Read `docs/CODEX_PUNE_CINEMAS_PROMPT.md` (your previous round) and the current code before you start.

## What changed since your last round (already done; do not redo)
- **Films.** `scripts/import_tmdb.py` now defaults to `--source pune`. It reads the hand-kept list
  `db/data/pune_now_showing.json` (35 films researched from public Pune listings), takes details from TMDB,
  imports films TMDB doesn't know yet without a poster (matched on title), and hides every other film. It has
  been run, so the database has 35 active films. Don't change the selection logic.
- **Cinemas.** `db/data/pune_cinemas_curated.json` holds the 20 real Pune cinemas currently selling tickets on a
  public booking platform. Names are as they appear there, for example "PVR Phoenix Marketcity",
  "INOX Bund Garden" and "Cinépolis Seasons Mall". Coordinates come from OpenStreetMap's Nominatim geocoder.
  **It replaces the OpenStreetMap list as the source of truth.** Many OSM entries had generic or invented names
  ("PVR INOX Ajmera") or tiny localities ("Happy Colony") for areas, and some are cinemas that have closed.
- The frontend already uses your cinema API: `/cinemas`, `/cinemas/{id}`, `/cinemas/{id}/shows`,
  `/movies/{id}/show-dates` and the cinema fields on shows, bookings and holds.

Customers still see a **demo**: real cinema names and locations, but simulated showtimes, prices and seats, and
tickets that are not valid for entry. Keep every customer-facing text consistent with that.

---

## Part A: curated cinemas become the source of truth

1. **Migration `010_cinema_source.sql`.** Add `cinemas.source_key TEXT UNIQUE` (the `key` from the curated
   file) and `cinemas.location_precision TEXT CHECK (location_precision IN ('building','area'))`.
2. **`scripts/import_cinemas.py`.** Add `--source curated`, which is the new default; the OSM import stays as
   `--source osm`.
   - Upsert every entry of `db/data/pune_cinemas_curated.json` on `source_key`, setting name, chain, area,
     address, coordinates and precision.
   - Mark **every other cinema** `is_active = FALSE`. That includes the OSM-imported ones and the legacy demo
     cinema. Never delete a cinema, screen or seat that has bookings or holds. Delete the **unbooked, unheld
     future shows** of inactive cinemas.
   - **Screens:** when the entry's `screens` is null, use the chain default: PVR INOX 5, Cinépolis 6, MovieMax 4,
     City Pride 4, Rajhans 3, Miraj 3, Mukta A2 3, Independent 1. Audis are named `Audi 1…n`. Two exceptions:
     - "PVR Director's Cut, KOPA Mall" and "MovieMax Gold, Mariplex Mall" are all-recliner luxury cinemas:
       4 screens, all using the lounge layout.
     - "Cinépolis Seasons Mall" includes a VIP section: make its last audi `VIP` with the lounge layout.
   - **Formats:** do **not** invent IMAX, ICE or 4DX at real cinemas. Every screen is `2D` unless the entry's
     `formats` lists one. Dolby Atmos may be used as a generic sound label at PVR INOX and Cinépolis.
   - Then run the programme scheduler, so the new cinemas have shows and inactive ones have none.
3. Add `location_precision` to the `Cinema` API model (additive).
4. `scripts/setup_local.py` uses the curated import, which works offline because it is a local file.

## Part B: realistic seat layouts driven by editable files

### B1. The layout file format (`db/data/seat_layouts/*.json`)
```jsonc
{
  "name": "Multiplex – medium",
  "description": "Front regular block, Prime middle, recliner back row, side aisles",
  // Front row first (nearest the screen). Each row is "<label> <pattern>".
  // Pattern characters: R = regular, P = premium ("Prime"), L = recliner,
  // W = wheelchair-accessible regular seat, '.' = aisle or gap (takes a column, no seat).
  // Seat numbers count left to right within a row, skipping gaps: "R.RR" gives seats 1, 2 and 3.
  "rows": [
    "A RRRR.RRRRRRRRRR.RRRR",
    "B RRRR.RRRRRRRRRR.RRRR",
    "...",
    "K PPPP.PPPPPPPPPP.PPPP",
    "L ...LLLL.LLLLLL.LLLL..."
  ],
  "section_names": {"R": "Regular", "P": "Prime", "L": "Recliner"}
}
```
- Write a strict validator, `app/seat_layouts.py`. It checks:
  - row labels are unique and in the form `[A-Z]+`, and the pattern uses only `RPLW.`;
  - every row is the same width, so columns line up across rows (pad with `.`);
  - there are at least 1 and at most 30 rows, at most 40 columns, and at least one seat.
  A bad file must fail with a clear message naming the file and the row.
- **Ship these templates.** They should look like real Indian cinemas, with **aisles that line up across
  rows**. A real hall has staggered row widths, so give the front rows fewer seats.

  | Template | Seats | Shape |
  |---|---|---|
  | `multiplex-small` | ≈ 120 | 10 rows, one centre aisle, last row recliners |
  | `multiplex-medium` | ≈ 200 | 12 rows, two side aisles, rows J–K Prime, last row recliners |
  | `multiplex-large` | ≈ 300 | 15 rows, two aisles, a cross-aisle (an empty row of `.`) after row F, last 2 rows recliners |
  | `lounge` | ≈ 40 | 4–5 rows of recliners in pairs (`LL.LL.LL…`) |
  | `single-screen` | ≈ 550 | 20 rows. Front 13 regular, then a cross-aisle, then 6 premium "balcony" rows. Two aisles. |

  Every multiplex template puts 2 `W` seats on the front row's aisle ends.
- **Per-screen overrides.** If `db/data/seat_layouts/screens/<cinema source_key>/<screen name>.json` exists,
  for example `screens/pune-pvr-phoenix-marketcity/Audi 1.json`, it is used instead of the template. This is how
  the developer will enter a real hall's layout. Create the folder with a `README.md` explaining the format.
- **Template assignment** must be deterministic:
  - lounge cinemas and VIP audis → `lounge`;
  - Independent single screens → `single-screen`;
  - multiplexes → `multiplex-large` for Audi 1, `multiplex-medium` for Audi 2–3, `multiplex-small` for the rest.

### B2. Schema (migration `011_seat_layouts.sql`)
- `seats.seat_type` CHECK becomes `('REGULAR','PREMIUM','RECLINER')`.
- New `seats` columns:
  - `row_index INTEGER` (0 = front)
  - `col INTEGER` (1-based grid column, gaps included)
  - `accessible BOOLEAN NOT NULL DEFAULT FALSE`
- `screens.layout_name TEXT` records which template or override built the screen.
- `shows.recliner_price NUMERIC(10,2)` (nullable). The scheduler sets it to **premium × 1.8, rounded to ₹10**,
  on screens that have recliners.
- The price everywhere (seat map, holds, bookings, availability) uses `recliner_price` for `RECLINER` seats.
  Search for every place that picks a price from `seat_type` (holds, bookings, `availability.py`,
  `chat_engine.py`, the worker email) and update them all.
- **Building seats.** When a screen is created, or when `--relayout` is passed to the import and the screen has
  **no bookings and no live holds**, delete its seats and rebuild them from the layout. Never touch a screen with
  bookings. Legacy screens keep their seats (`row_index` and `col` stay null).

### B3. API contract (additive; the frontend builds against it now)
`GET /shows/{id}/seats`, `SeatInShow`, gains:
```jsonc
"seat_type": "REGULAR" | "PREMIUM" | "RECLINER",   // new value RECLINER
"row_index": 0,          // 0 = front row; null for legacy screens
"col": 5,                // 1-based grid column including gaps; null for legacy screens
"accessible": false
```
`SeatMap` gains:
```jsonc
"layout_name": "multiplex-medium",
"grid": {"rows": 12, "cols": 24},          // null for legacy screens
"sections": [                             // back of the hall first, as cinemas list them
  {"name": "Recliner", "seat_type": "RECLINER", "price": "720.00", "row_labels": ["L"]},
  {"name": "Prime",    "seat_type": "PREMIUM",  "price": "400.00", "row_labels": ["J", "K"]},
  {"name": "Regular",  "seat_type": "REGULAR",  "price": "250.00", "row_labels": ["A", "B", "...", "I"]}
]
```
`HeldSeat`, `BookingSeat` and every other `seat_type` field accept `RECLINER`. `ShowSummary` gains
`"recliner_price"` (nullable).

## Part C: film admin API (the frontend builds `/admin` against this)

Its job: each week, someone ticks which films are playing in Pune and adds new releases, without editing JSON.

- **Accounts.** Use the existing `admin_users` table. Add `scripts/create-admin.ps1` (wrapping
  `scripts/create_admin.py`), which prompts for a username and a password (hidden input via `getpass`) and stores
  `scrypt` from Python's `hashlib`, with a random salt, in the form `scrypt$n$r$p$salt$hash`. Never log passwords.
- **Sessions:** migration `012_admin_sessions.sql` creates
  `admin_sessions(token_hash TEXT PRIMARY KEY, admin_user_id BIGINT REFERENCES admin_users(id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())`. Tokens are 32 random bytes in
  url-safe base64. Store only their SHA-256. Sessions last 12 hours.
- **Endpoints** (all under the API prefix; every `/admin/*` call except login requires
  `Authorization: Bearer <token>`, and returns 401 `{"detail": "Please sign in again"}` otherwise):
  - `POST /admin/login` `{username, password}` → `{"token": "...", "expires_at": "...", "username": "..."}`.
    Wrong credentials → 401 `{"detail": "Wrong username or password"}`. Rate limit: 10 failures per 15 minutes
    per IP, the same pattern as `demo_phone.py`.
  - `POST /admin/logout` → 204 (deletes the session).
  - `GET /admin/movies` → `list[AdminMovie]`: every **non-sample** movie, active first, then by title.
    `AdminMovie` = the `Movie` fields + `"is_active": bool`, `"tmdb_id": int | null`, `"upcoming_shows": int`.
  - `PATCH /admin/movies/{id}` `{"is_active": bool}` → `AdminMovie`. Activating schedules shows for the film
    straight away, calling the scheduler for that one film. Deactivating frees its unbooked, unheld future shows.
    Booked shows stay.
  - `GET /admin/tmdb/search?q=` → `[{"tmdb_id", "title", "original_language", "release_date", "poster_url"}]`
    (at most 10). The TMDB key stays on the server and is never sent to the browser. If no key is configured →
    503 `{"detail": "TMDB_API_KEY is not set on the server"}`.
  - `POST /admin/movies` `{"tmdb_id": int | null, "title": str, "language": str, "certificate": "U"|"UA"|"A"}` →
    201 `AdminMovie`. With a `tmdb_id`, load the details through the same function `scripts/import_tmdb.py` uses
    (`details()`); move it into an importable module if needed, but keep the script working. Without a
    `tmdb_id`, create the film with no poster, as the importer does. The new film is active and scheduled.
- **Persistence note.** Admin changes are the live state. Running `.\scripts\import-movies.ps1` again is a full
  refresh from `db/data/pune_now_showing.json`. Say so in the README, and add
  `GET /admin/movies/export` → the JSON in the `pune_now_showing.json` format, built from the active films, so the
  developer can save the admin's choices back into the file.
- Never cache admin responses. Every admin action is logged at INFO with the admin's username and the movie id.

## Part D: customer text
- Update `help_info.json` for the 20 real cinemas: seat types (Regular, Prime, Recliner, wheelchair-accessible
  seats), and the demo notice. The chat assistant reads this file, so re-run the chat tests and
  `backend/eval/chat_eval.py` with the fake provider.
- Emails and SMS show "Recliner" seats correctly.

## Tests (required, offline)
- The curated import: upsert, deactivation, booked shows untouched, no invented formats, the lounge cinemas.
- The layout validator, with good and bad files and the error messages; every shipped template is valid and has
  aligned aisles; the per-screen override wins; seat numbering skips gaps; `--relayout` skips booked screens.
- Recliner pricing all the way through: seat map → hold → booking → email total.
- `GET /shows/{id}/seats` returns `row_index`, `col`, `accessible`, `grid` and `sections`, with sections back to
  front; legacy screens get null `grid` and `col`.
- Admin:
  - login success and failure, rate limit, expired token, no token, logout;
  - activate, deactivate (booked shows kept), add with and without a TMDB id (TMDB faked), export.
- The end-to-end local booking of a RECLINER seat at a curated cinema.

## Report back with
1. Changed and added files, by Part.
2. The commands, in order. Expect: `.\scripts\setup-local.ps1` (migrations), `.\scripts\import-cinemas.ps1`,
   `.\scripts\create-admin.ps1`, then restart the API.
3. Pytest summary lines.
4. The cinema, screen, seat and show counts after a real run.
5. Any deviation from the B3 or C contracts.
