# CineBook - operations guide

A training booking system with 20 curated real Pune cinema locations and simulated programmes,
prices and editable seat maps. **DEMO TICKET - not valid for entry.** CineBook is not affiliated
with the cinemas. Start with [START-HERE.md](../START-HERE.md) for workstation and local-mode setup.

## Update the backend

From the repository root in Windows PowerShell 5.1:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-local.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\import-cinemas.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\create-admin.ps1
```

Setup applies outstanding migrations without resetting existing data. The cinema importer defaults
to the offline `db/data/pune_cinemas_curated.json` file. OSM is an explicit alternate source:
`import-cinemas.ps1 -Source osm`; add `-Offline` to load its saved snapshot. Switching source
deactivates other venues and removes only unbooked, unheld future shows. Historic cinemas, screens,
seats, bookings and held shows remain readable.

Admin creation prompts for a username and a hidden password. Reusing a username resets its password
and revokes existing sessions. No default account or password is shipped. Stop the existing API
with Ctrl+C, then restart it:

```powershell
Push-Location backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

## Editable seats

Templates are in `db/data/seat_layouts/`. They include Regular, Prime and Recliner seats, accessible
Regular seats, and aligned aisles. These are training plans, not verified real auditorium maps.
Override an individual screen at `db/data/seat_layouts/screens/<source_key>/<screen name>.json`.
The [layout format guide](../db/data/seat_layouts/screens/README.md) includes a complete example.

An ordinary import preserves existing seat ids and layouts. After editing a template or override:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\import-cinemas.ps1 -Relayout
```

Relayout skips every screen with any booking, including cancelled bookings, or a live hold. It
preserves legacy cinema seats. Section names and grid dimensions are persisted with screens so
the running API needs no layout JSON files. Recliners use the show's recliner price; the scheduler
sets it to 1.8 times Premium, rounded to INR 10. Legacy maps have null grid positions.

## Film admin and persistence

Log in with `POST /admin/login`. Send `Authorization: Bearer <token>` on all other admin requests.
Sessions expire after 12 hours and are revoked by logout. The database stores scrypt password hashes
and SHA-256 token hashes. Admin responses are never cached. Existing API prefixes also apply here.

`GET /admin/movies` lists active and inactive non-sample films. Activate or deactivate a film with
`PATCH /admin/movies/{id}`. Activation schedules that film immediately, replacing only unbooked,
unheld future slots where needed and preserving the other films' daily coverage. Deactivation
preserves booked and held shows. Add a film using `POST /admin/movies`, with a TMDB id or manually.
TMDB search/details require `TMDB_API_KEY` in `backend/.env`; the key is
never returned to the browser.

**Admin changes are the live database state. Running `scripts/import-movies.ps1` again fully
refreshes film selection from `db/data/pune_now_showing.json`.** It can deactivate admin-added films
and reactivate films still in the file. To preserve the admin's weekly selections, save the JSON
returned by `GET /admin/movies/export` as `db/data/pune_now_showing.json` before the next import.
The film importer's Pune/India selection and matching rules are unchanged.

## Weekly demo programmes

Programmes follow a Friday-to-Thursday booking week. Each cinema keeps its films and screen times
through the week; the next week carries over its active films. The scheduler publishes today
through today + 7, with only future slots today. Times, prices and tickets remain simulated.
Admin activation adds a film at two or more cinemas for the remaining week; deactivation gives
unprotected slots to its screen partner or the cinema's leading film. Bookings and live holds
always keep their shows and block overlapping slots.

To replace an older per-day schedule once, run from the repository root:

```powershell
.\scripts\schedule-shows.ps1 -Rebuild
```

If script execution is disabled, use
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\schedule-shows.ps1 -Rebuild`.
Rebuild removes all unbooked, unheld future shows at active cinemas before publishing the weekly
plans. Ordinary setup/import runs use the non-rebuild scheduler. Running
`.\scripts\schedule-shows.ps1` immediately afterwards creates and deletes zero shows.
The [recorded local rebuild report](weekly-programme-report.json) includes daily coverage,
Rajhans times and the protected show kept outside its cinema's weekly line-up.

## Verification

```powershell
.\.venv\Scripts\python -m pytest backend
.\.venv\Scripts\python -m pytest worker
.\.venv\Scripts\python backend\eval\chat_eval.py --provider fake --delay 0
```

Tests fake TMDB and model calls; database tests use local PostgreSQL and skip when it is
unreachable. Fake-provider evaluation checks API, context and response handling, not model quality.
