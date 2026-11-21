# CineBook - start here

## Why this package exists
It is a complete, working example of a small full-stack application, shared so that you can study it
and run it on your own computer.

## What it is
CineBook is a movie ticket booking system: a customer picks seats, pays (simulated), receives a confirmation
email and a demo SMS with a link, and can ask a chat assistant about the booking.

## What it is for
Learning and training. It was built one step at a time.
It is not a production system and it holds no real customer data.

## Which parts it contains
| Folder | What it is | Technology |
|---|---|---|
| `backend` | The API, including the chat assistant | Python, FastAPI |
| `frontend` | The website | React (Vite) |
| `worker` | Confirms bookings, writes the demo SMS and the email | Python (runs inside the API process) |
| `db` | Database structure, sample data, upgrades and tests | PostgreSQL |
| `scripts` | Setup, run, import and admin helpers | PowerShell, Python |
| `docs` | Design notes, the operations guide and the project journal | - |

## What you need

1. A Windows computer with Python 3.12 or 3.13, Node 24, PostgreSQL 16 or newer, and Git.
   `check-tools.ps1` checks that they are installed.
2. Optional: your own Gemini API key for the chat assistant. The free tier is enough.
3. Optional: a free TMDB API key to import the current film listings.

## Run it

In PowerShell 5.1, from the project root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements-dev.txt
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
notepad backend\.env
```

Set `DATABASE_URL` to your local PostgreSQL credentials. Keep `API_PREFIX` empty. Set `SMS_DEMO_NUMBERS`
and `DEMO_PHONE_ACCESS_CODE` for the demo inbox (or run `.\scripts\setup-demo-sms.ps1`). A Gemini key is
optional; without a configured model the SMS link and booking summary still work, but conversational
replies require a model. `python scripts\check-gemini.py` checks a key and saves a working model.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-local.ps1
Push-Location frontend
npm ci
Pop-Location
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-local.ps1
```

Open http://localhost:5173 (API docs: http://localhost:8000/docs). The two terminal windows run the API
and frontend; close them to stop. Booking confirmation runs inside the API process, right after each booking.
Seat holds are stored in PostgreSQL. Demo emails are saved in `backend/outbox/`. Re-run setup to apply
outstanding migrations and add shows for today. Existing data is preserved. `setup-local.ps1 -Reset` asks
for `RESET` before deleting data.
The commands above allow scripts for those processes only, so they work with Windows' default
restricted execution policy without changing your machine's policy. If a database password contains
`@`, encode it as `%40` in `DATABASE_URL` (and encode other URL reserved characters similarly).

## Real Pune cinemas, demo programmes

The default directory is the 20-venue curated list in `db/data/pune_cinemas_curated.json`.
OpenStreetMap remains an optional alternate source. CineBook
has no affiliation with these venues. Every showtime, price, auditorium and seat map is generated
for training: **DEMO TICKET - not valid for entry**. The curated file controls the default venue names and areas. OSM can include closed venues;
use its override file when importing that alternate source. Facilities and admission rules are not supplied by CineBook.

From the project root, refresh in this order, then restart the API with Ctrl+C and the final command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\import-cinemas.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\import-movies.ps1
Push-Location backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

`import-movies.ps1` uses `TMDB_API_KEY` in `backend/.env`; film-selection logic is unchanged.
For offline setup, `setup-local.ps1` imports the curated local file and schedules existing active
films without any network calls. Use `import-cinemas.ps1 -Source osm -Offline` for the old OSM snapshot.
`-DryRun` previews the chosen source without database writes; online OSM mode also saves its snapshot. Repeated imports preserve existing seat layouts and shows, including bookings and live holds.
See [docs/OPERATIONS.md](docs/OPERATIONS.md) for editable layouts, protected `-Relayout`, admin account creation and
the live film-admin/export workflow.
`db/data/pune_cinemas_overrides.json` supports `exclude`, `rename`, and `area` overrides keyed by OSM id.

The programme gives each active film at least two shows per full day across the city. A first import
late today may have insufficient remaining slots before 23:15; it never invents past showtimes.
Prices add 15% of base for Friday–Sunday and another 15% after 18:00, then multiply premium formats
by 1.6 and round to INR 10. New programmes use deterministic seeds rather than Python's randomised hash.

Attribution: [OpenStreetMap contributors, ODbL](https://www.openstreetmap.org/copyright).
Overpass query output and mirrors follow the [Overpass QL reference](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL).
Movie metadata uses the TMDB API; CineBook is not endorsed or certified by TMDB.

## What is deliberately NOT in this package
Every secret and every personal detail has been removed. You create your own:

| You create | How |
|---|---|
| `backend\.env` and `worker\.env` | Copy each `.env.example` to `.env` and fill in your values |
| `frontend\.env` | Copy `frontend\.env.example` to `frontend\.env` |
| Database password | You choose it when you install PostgreSQL |
| Demo phone numbers and Demo Phone access code | `.\scripts\setup-demo-sms.ps1` |
| Gemini API key | `python scripts\check-gemini.py` |
| TMDB API key | Free key from [TMDB settings](https://www.themoviedb.org/settings/api), saved as `TMDB_API_KEY` |

Folders that are rebuilt on your computer and are therefore not included:
`.venv`, `frontend\node_modules`, `frontend\dist`, `backend\outbox`.

## Keep it safe
- Never put a `.env` file into Git, email or chat. The `.gitignore` file in this package already excludes them.
- Never paste an API key or a password anywhere except the prompt of the script that asks for it.

## Customer accounts and the admin console
- **Customers** create an account at `/register` (email + password). Browsing is open; holding seats and paying
  need a signed-in account, and every booking is linked to it (`/my-bookings`). Set `REQUIRE_LOGIN_FOR_BOOKING=false`
  in `backend/.env` to allow guest booking again.
- **Staff** sign in at `/admin` (accounts from `.\scripts\create-admin.ps1`, or added by a super admin under
  *Staff & roles*). Roles:

  | Role | Can |
  |---|---|
  | Super admin | Everything, including staff accounts and the audit log |
  | Manager | Films, cinemas and shows (including cancelling a show), blocking customers, plus Support's rights |
  | Support | Dashboard, bookings and customers; cancel and refund a booking |

- Every staff change is recorded in the **audit log** (`admin_audit_log`). The rules live in
  `backend/app/permissions.py` and are enforced by the API; the website only hides what a role cannot use.
- Database change: `db/migrations/013_accounts_roles_audit.sql` (run `.\scripts\setup-local.ps1` on another machine).
