# 🎬 CineBook

[![CineBook checks](https://github.com/saikishorr/cinebook/actions/workflows/ci.yml/badge.svg)](https://github.com/saikishorr/cinebook/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.165-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%2B-4169E1?logo=postgresql&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white)

CineBook is a full-stack movie ticket booking system, built step by step as a learning and training
project. A customer browses real Pune cinemas, picks seats on a live seat map, holds them for 5 minutes,
pays (simulated) and gets a confirmation email plus a demo SMS. The SMS links to a chat assistant
that answers questions about that booking.

> **Training project.** Every showtime, price, auditorium and seat map is generated.
> **DEMO TICKET - not valid for entry.** CineBook is not affiliated with any cinema, and no real SMS,
> email or payment is ever sent.

---

## Features

**For customers**
- Browse now-showing films (TMDB metadata) and 20 curated real Pune cinemas.
- Weekly programmes (Friday to Thursday) with day tabs and showtimes per cinema.
- Interactive seat maps with Regular, Prime, Recliner and accessible seats, and aisles.
- 5-minute seat holds with a countdown, so two people can never book the same seat.
- Dynamic pricing: weekend and evening surcharges, and premium formats.
- Accounts (`/register`, `/my-bookings`), find a booking, and cancellation with a cut-off time.
- Confirmation email and a **demo SMS** with a link to a booking-aware **chat assistant** (Gemini).
- A Help page, plus a "Demo Phone" inbox that shows the SMS messages.

**For staff (admin console at `/admin`)**
- Dashboard, bookings, customers, films, cinemas and shows.
- Roles (Super admin, Manager, Support) enforced by the API, and an audit log of every staff change.
- Add films from TMDB or by hand; activating a film schedules it straight away.

**Engineering**
- Seat holds in PostgreSQL with a unique (show, seat) key and an expiry time, so a seat can never be double-booked.
- Confirmation runs right after each booking and is safe to repeat: nothing is charged twice, and no duplicate SMS is written.
- Stale pending bookings are swept automatically, which frees their seats.
- Versioned SQL migrations (with down scripts), rate limiting, structured logging with request IDs.
- Demo emails saved as `.eml` files in `backend/outbox/`, so nothing leaves your machine.
- CI on every push: ruff, pytest against a real PostgreSQL (Python 3.12 and 3.13), oxlint and a frontend build.

## Architecture

```mermaid
flowchart LR
    U[Customer / Staff browser] --> FE[React SPA<br/>Vite dev server :5173]
    FE -->|REST / JSON| API[FastAPI :8000]
    API --> DB[(PostgreSQL<br/>bookings, seat holds,<br/>chat links, SMS)]
    API -->|after each booking| W[Confirmation worker<br/>in-process]
    W --> DB
    W --> OUT[backend/outbox/<br/>demo emails]
    API --> LLM[Gemini API<br/>chat assistant]
    API -.->|import scripts| TMDB[TMDB / OpenStreetMap]
```

**Booking flow:** hold seats → create booking (`PENDING`) → confirmation worker marks it `CONFIRMED`,
writes the chat link and demo SMS, releases the hold and writes the email → the customer opens the SMS
link and chats with the assistant.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 19, React Router 7, Vite 8, Tailwind CSS 4, oxlint |
| Backend API | Python 3.12+, FastAPI, Uvicorn, Pydantic Settings, psycopg 3 |
| Database | PostgreSQL 16+ |
| AI | Google Gemini (free tier); a fake provider for tests |
| Data sources | TMDB (films), OpenStreetMap (cinema locations) |
| Tooling | PowerShell and Python scripts, ruff, pytest, GitHub Actions |

## Repository layout

| Folder | Contents |
|---|---|
| [`backend/`](backend) | FastAPI app (`app/`), routers, chat engine, tests, chat evaluation |
| [`frontend/`](frontend) | React website: customer pages, seat map, chat panel, admin console |
| [`worker/`](worker) | Booking confirmation and demo SMS, run by the API after each booking |
| [`db/`](db) | `schema.sql`, seed data, migrations `002` to `013`, cinema and seat-layout data, SQL tests |
| [`scripts/`](scripts) | Local setup and run, cinema/movie importers, show scheduler, admin creation, Gemini check |
| [`docs/`](docs) | Project journal, operations guide, design notes |

## Quick start

You need **Windows PowerShell 5.1**, **Python 3.12 or 3.13**, **Node 24** and **PostgreSQL 16+**.
(`check-tools.ps1` checks the installed tools.)

```powershell
# 1. Python environment
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements-dev.txt

# 2. Configuration: set DATABASE_URL (and optionally the demo SMS, Gemini and TMDB values)
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
notepad backend\.env

# 3. Database, cinemas and shows (applies migrations; keeps existing data)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-local.ps1

# 4. Frontend dependencies
Push-Location frontend; npm ci; Pop-Location

# 5. Optional: create a staff account for /admin
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\create-admin.ps1

# 6. Run the API and the website
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-local.ps1
```

| URL | What |
|---|---|
| http://localhost:5173 | Website |
| http://localhost:8000/docs | Interactive API docs (Swagger) |
| http://localhost:5173/admin | Admin console |

A Gemini key (`GEMINI_API_KEY`) is optional. Without it, bookings, SMS links and booking summaries
still work, but conversational chat replies need a model. `python scripts\check-gemini.py` checks a
key and saves a working model. `TMDB_API_KEY` is only needed to import films.
See [START-HERE.md](START-HERE.md) for the full walkthrough.

## Configuration

Copy each `.env.example` to `.env`. These are the main backend settings:

| Variable | Purpose | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@localhost:5432/moviebooking` |
| `HOLD_SECONDS` | Seat hold duration | `300` |
| `CORS_ORIGINS` | Allowed website origins | `http://localhost:5173` |
| `API_PREFIX` | Path prefix for the API (empty = `/`) | *(empty)* |
| `SMS_DEMO_NUMBERS` | Numbers allowed to receive a demo SMS | `+919800000000` |
| `DEMO_PHONE_ACCESS_CODE` | Code that opens the Demo Phone inbox | your choice |
| `CHAT_PROVIDER` / `CHAT_MODEL_ID` / `GEMINI_API_KEY` | Chat assistant model | `gemini` / model id / your key |
| `TMDB_API_KEY` | Film import and admin film search | your key |
| `CANCEL_CUTOFF_MINUTES` | Latest cancellation before the show | `120` |
| `REQUIRE_LOGIN_FOR_BOOKING` | Set `false` to allow guest booking | `true` |

> 🔒 Never commit `.env` files. The `.gitignore` already excludes them.

## Testing

```powershell
.\.venv\Scripts\python -m ruff check --config backend\pyproject.toml backend worker
.\.venv\Scripts\python -m pytest backend
.\.venv\Scripts\python -m pytest worker
.\.venv\Scripts\python backend\eval\chat_eval.py --provider fake --delay 0
Push-Location frontend; npm run lint; npm run build; Pop-Location
```

The tests use fakes for TMDB and model calls and never touch the network. Database tests use a local
PostgreSQL and are skipped when it is unreachable. With the real model, the chat assistant passed
**39 of 39** evaluation questions in 8 groups ([report](backend/eval/chat_eval_report.md)).

## Documentation

- [START-HERE.md](START-HERE.md): setup, what is (and is not) included, safety, accounts and roles
- [docs/OPERATIONS.md](docs/OPERATIONS.md): cinema/film imports, editable seat layouts, film admin, weekly programmes
- [docs/PROJECT-JOURNAL.md](docs/PROJECT-JOURNAL.md): how the project was built, decisions and problems solved
- [docs/phase3-chatbot-design.md](docs/phase3-chatbot-design.md): chat assistant design

## Project phases

| Phase | Scope |
|---|---|
| 1 | Booking system: database, API, seat holds, website, booking confirmation and email |
| 2 | Booking SMS with a chat link (demo inbox, consent, rate limits) |
| 3 | Chat assistant (Gemini): booking-aware, read-only, refuses off-topic questions |
| 4 | Real Pune cinemas, editable seat layouts, weekly programmes, TMDB films, customer accounts, role-based admin console and audit log |

## Acknowledgements

- Cinema locations: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL.
- Movie metadata from [TMDB](https://www.themoviedb.org/). This product uses the TMDB API but is not endorsed or certified by TMDB.

## Author

**Saikishor**: [@saikishorr](https://github.com/saikishorr)
