# 🎬 CineBook

[![CineBook checks](https://github.com/saikishorr/cinebook/actions/workflows/ci.yml/badge.svg)](https://github.com/saikishorr/cinebook/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.165-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%2B-4169E1?logo=postgresql&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-ap--south--1-FF9900?logo=amazonaws&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-IaC-7B42BC?logo=terraform&logoColor=white)

CineBook is a full-stack movie ticket booking system built step by step on AWS as a learning and
training project. A customer browses real Pune cinemas, picks seats on a live seat map, holds them for
5 minutes, pays (simulated) and gets a confirmation email plus a demo SMS. The SMS links to a chat
assistant that answers questions about that booking.

> **Training project.** Every showtime, price, auditorium and seat map is generated.
> **DEMO TICKET - not valid for entry.** CineBook is not affiliated with any cinema, and no real SMS
> or payment is ever sent.

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
- Pluggable backends: seat holds in **DynamoDB or PostgreSQL**, bookings through **SQS or inline**,
  email through **SES or a local outbox**. The whole app runs locally with no AWS account.
- Idempotent booking worker that runs locally or as **AWS Lambda**, and handles duplicate SQS deliveries safely.
- Versioned SQL migrations (with down scripts), rate limiting, structured logging.
- Infrastructure as code (Terraform) with a single `running` switch that pauses the paid resources.
- CI on every push: ruff, pytest against a real PostgreSQL (Python 3.12 and 3.13), oxlint and a frontend build.

## Architecture

```mermaid
flowchart LR
    U[Customer / Staff browser] --> CF[CloudFront + S3<br/>React SPA]
    CF -->|/api| ALB[Application Load Balancer]
    ALB --> API[FastAPI on EC2<br/>Docker, Auto Scaling]
    API --> RDS[(RDS PostgreSQL)]
    API --> DDB[(DynamoDB<br/>seat holds)]
    API --> SQS[[SQS FIFO<br/>booking-requests]]
    API --> LLM[Gemini API<br/>chat assistant]
    SQS --> L[Lambda worker]
    L --> RDS
    L --> DDB
    L --> SES[SES email]
    L --> SMS[(Demo SMS +<br/>chat link)]
    API -.-> CW[CloudWatch<br/>logs, dashboard, alarm]
    L -.-> CW
```

All cloud resources live in a VPC (public, app and database subnets) in `ap-south-1` (Mumbai). A NAT
instance is used instead of a NAT gateway to keep costs low. In **local mode** the same API uses
PostgreSQL for holds, runs the worker inline and writes emails to `backend/outbox/`.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 19, React Router 7, Vite 8, Tailwind CSS 4, oxlint |
| Backend API | Python 3.12+, FastAPI, Uvicorn, Pydantic Settings, psycopg 3 |
| Worker | Python (AWS Lambda with an SQS trigger, or local) |
| Data | PostgreSQL (RDS), DynamoDB |
| AI | Google Gemini (free tier); a fake provider for tests |
| Cloud | VPC, EC2 Auto Scaling, ALB, ECR, RDS, DynamoDB, SQS, Lambda, SES, SSM Parameter Store, CloudFront, CloudWatch |
| IaC and ops | Terraform, Docker, PowerShell and Python scripts |
| CI | GitHub Actions |

## Repository layout

| Folder | Contents |
|---|---|
| [`backend/`](backend) | FastAPI app (`app/`), routers, chat engine, tests, chat evaluation, Dockerfile |
| [`frontend/`](frontend) | React website: customer pages, seat map, chat panel, admin console |
| [`worker/`](worker) | Booking confirmation worker (SQS to PostgreSQL, DynamoDB and SES) and demo SMS |
| [`db/`](db) | `schema.sql`, seed data, migrations `002` to `013`, cinema and seat-layout data, SQL tests |
| [`infra/`](infra) | Terraform, IAM policies, EC2 user data, CloudFront, monitoring, pause/resume scripts |
| [`scripts/`](scripts) | Local setup and run, cinema/movie importers, show scheduler, admin creation |
| [`guides/`](guides) | 16 step-by-step Word guides (Part 1 to Part 16) |
| [`docs/`](docs) | Project journal, operations guide, design notes |

## Quick start (local, no AWS)

Requirements: **Windows PowerShell 5.1**, **Python 3.12 or 3.13**, **Node 24**, **PostgreSQL 16+**.
(`check-tools.ps1` checks the installed tools.)

```powershell
# 1. Python environment
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements-dev.txt

# 2. Configuration: set DATABASE_URL and uncomment the "Local mode" lines
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

A Gemini key (`GEMINI_API_KEY`) is optional: without it, bookings, SMS links and booking summaries
still work, but conversational chat replies need a model. `TMDB_API_KEY` is only needed to import films.
See [START-HERE.md](START-HERE.md) for the full walkthrough.

## Configuration

Copy each `.env.example` to `.env`. These are the main backend settings:

| Variable | Purpose | Local value |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@localhost:5432/moviebooking` |
| `HOLDS_BACKEND` | `dynamodb` or `postgres` | `postgres` |
| `QUEUE_BACKEND` | `sqs` or `inline` | `inline` |
| `EMAIL_BACKEND` | `ses` or `log` | `log` |
| `HOLD_SECONDS` | Seat hold duration | `300` |
| `CORS_ORIGINS` | Allowed website origins | `http://localhost:5173` |
| `API_PREFIX` | Empty locally, `/api` in the cloud | *(empty)* |
| `SMS_DEMO_NUMBERS` | Numbers allowed to receive demo SMS | `+919800000000` |
| `DEMO_PHONE_ACCESS_CODE` | Code that opens the Demo Phone inbox | your choice |
| `CHAT_PROVIDER` / `CHAT_MODEL_ID` / `GEMINI_API_KEY` | Chat assistant model | `gemini` / model id / your key |
| `TMDB_API_KEY` | Film import and admin film search | your key |
| `REQUIRE_LOGIN_FOR_BOOKING` | Set `false` to allow guest booking | `true` |

> 🔒 Never commit `.env`, `demo.auto.tfvars` or `terraform.tfstate`. The `.gitignore` already excludes them.

## Testing

```powershell
.\.venv\Scripts\python -m ruff check --config backend\pyproject.toml backend worker
.\.venv\Scripts\python -m pytest backend
.\.venv\Scripts\python -m pytest worker
.\.venv\Scripts\python backend\eval\chat_eval.py --provider fake --delay 0
Push-Location frontend; npm run lint; npm run build; Pop-Location
```

The tests use fakes for TMDB, AWS and model calls. Database tests use a local PostgreSQL and are skipped
when it is unreachable. With the real model, the chat assistant passed **39 of 39** evaluation questions
in 8 groups ([report](backend/eval/chat_eval_report.md)).

## Deploying to AWS

The cloud build follows guides **Part 7 to Part 16** in [`guides/`](guides). In short:

1. Build and push the API image to ECR (`backend/Dockerfile`).
2. Fill in your own values (`<ACCOUNT_ID>`, AMI, sender email, `demo.auto.tfvars`) and run Terraform in `infra/terraform`.
3. Package the Lambda worker with `infra/lambda/build.ps1`.
4. Store secrets in SSM Parameter Store (`infra/scripts/setup-demo-sms.ps1`, `push-chat-key.py`).
5. Use `infra/scripts/pause.ps1` / `resume.ps1` to stop and start the hourly-billed resources.

While it is running, the system costs about **USD 0.08 per hour**. Pause it whenever you stop working.

## Documentation

- [START-HERE.md](START-HERE.md): setup, what is (and is not) included, guide order, cost, safety
- [docs/OPERATIONS.md](docs/OPERATIONS.md): cinema/film imports, editable seat layouts, film admin, weekly programmes
- [docs/PROJECT-JOURNAL.md](docs/PROJECT-JOURNAL.md): how the project was built, decisions and problems solved
- [docs/phase3-chatbot-design.md](docs/phase3-chatbot-design.md): chat assistant design
- [CineBook-Complete-Project-Documentation.pdf](CineBook-Complete-Project-Documentation.pdf): all guides in one PDF
- [`guides/`](guides): Part 1 to Part 16 Word guides (Part 12, CloudFront, is not included)

## Project phases

| Phase | Scope |
|---|---|
| 1 | Booking system on AWS: database, API, seat holds, website, SQS/Lambda/SES, Docker, VPC, RDS, EC2, ALB, Terraform |
| 2 | Booking SMS with a chat link (demo inbox, consent, rate limits) |
| 3 | Chat assistant (Gemini): booking-aware, read-only, refuses off-topic questions |
| 4 | Real Pune cinemas, editable seat layouts, weekly programmes, TMDB films, customer accounts, role-based admin console and audit log |

## Acknowledgements

- Cinema locations: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL.
- Movie metadata from [TMDB](https://www.themoviedb.org/). This product uses the TMDB API but is not endorsed or certified by TMDB.

## Author

**Saikishor**: [@saikishorr](https://github.com/saikishorr)
