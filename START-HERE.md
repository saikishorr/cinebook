# CineBook - start here

## Why this package exists
It is a complete, working example of a small cloud application, handed over so that you can study it,
run it on your own computer and build your own copy in your own AWS account.

## What it is
CineBook is a movie ticket booking system: a customer picks seats, pays (simulated), receives a confirmation
email and a demo SMS with a link, and can ask a chat assistant about the booking.

## What it is for
Learning and training. It was built one step at a time, and every step has a written guide.
It is not a production system and it holds no real customer data.

## Which parts it contains
| Folder | What it is | Technology |
|---|---|---|
| `backend` | The API, including the chat assistant | Python, FastAPI |
| `frontend` | The website | React (Vite) |
| `worker` | Confirms bookings, sends the email, writes the demo SMS | Python (runs locally or as AWS Lambda) |
| `db` | Database structure, sample data, upgrades and tests | PostgreSQL |
| `infra` | AWS infrastructure and helper scripts | Terraform, PowerShell, Python |
| `guides` | 16 step-by-step Word guides | - |
| `docs` | Design notes and the project journal | - |

## What you need
1. A Windows computer with the tools in `guides\Project-Software-Installation-Guide.docx`.
   `check-tools.ps1` checks that they are installed.
2. Your own AWS account (Part 1 of the guides).
3. Your own Gemini API key for the chat assistant (Part 16). The free tier is enough.

## Run locally without AWS

Python 3.12 or 3.13, Node 24 and PostgreSQL 18 are enough. In PowerShell 5.1, from the project root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements-dev.txt
Copy-Item backend\.env.example backend\.env
notepad backend\.env
```

Set `DATABASE_URL` to your local PostgreSQL credentials. Uncomment the four Local mode settings:
`HOLDS_BACKEND=postgres`, `QUEUE_BACKEND=inline`, `EMAIL_BACKEND=log`, and the localhost `CORS_ORIGINS`.
Keep `API_PREFIX` empty. Set `SMS_DEMO_NUMBERS` and `DEMO_PHONE_ACCESS_CODE` for the demo inbox.
No AWS queue URL or credentials are used in inline mode. A Gemini key is optional; without a configured
model the SMS link and booking summary still work, but conversational replies require a model.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-local.ps1
Push-Location frontend
npm ci
Pop-Location
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-local.ps1
```

Open http://localhost:5173 (API docs: http://localhost:8000/docs). The two terminal windows run the API
and frontend; close them to stop. Confirmation runs in the API process; do not start the SQS worker.
Demo emails are saved in `backend/outbox/`. Re-run setup to apply outstanding migrations and add shows
for today. Existing data is preserved. `setup-local.ps1 -Reset` asks for `RESET` before deleting data.
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

| You create | How | Guide |
|---|---|---|
| `backend\.env` and `worker\.env` | Copy each `.env.example` to `.env` and fill in your values | Parts 3 and 6 |
| `frontend\.env` | Copy `frontend\.env.example` to `frontend\.env` | Part 5 |
| Database password | You choose it; it is stored in AWS Parameter Store | Part 9 |
| Demo phone numbers and Demo Phone access code | `infra\scripts\setup-demo-sms.ps1` | Part 15 |
| Gemini API key | `infra\scripts\check-gemini.py`, then `infra\scripts\push-chat-key.py` | Part 16 |
| Sender email address | Verify your own address in SES; set `ses_sender_email` in `infra\terraform\variables.tf` | Parts 6 and 14 |
| Terraform state | Created by Terraform in your own account; never share it | Part 14 |

Placeholders to replace with your own values:
- `you@example.com` in `infra\terraform\variables.tf`
- `<ACCOUNT_ID>` in `infra\iam\*.json`
- `<AMI_ID>` and `<APP_SECURITY_GROUP_ID>` in `infra\ec2\launch-template.json`

Folders that are rebuilt on your computer and are therefore not included:
`.venv`, `frontend\node_modules`, `frontend\dist`, `worker\build`, `worker\lambda.zip`, `infra\terraform\.terraform`.

## The order to work in
The code is complete. Use the guides to understand each part and to create your own AWS resources.
Where a guide asks you to write a file, the finished file is already in this package.

| Guide | What it builds |
|---|---|
| Part 1 | Workstation and AWS account setup |
| Part 2 | PostgreSQL database on your computer |
| Part 3 | Backend API |
| Part 4 | Seat holds in DynamoDB |
| Part 5 | React website |
| Part 6 | Bookings through a queue, a worker and email |
| Part 7 | Docker image in ECR |
| Part 8 | VPC network |
| Part 9 | RDS database in AWS |
| Part 10 | EC2 Auto Scaling |
| Part 11 | Load balancer |
| Part 13 | Lambda worker and monitoring |
| Part 14 | Terraform, with pause and resume |
| Part 15 | Booking SMS with a chat link (demo inbox) |
| Part 16 | Chat assistant |

Notes:
- **Part 12 (CloudFront, the public website address) is not included.** Until you add it, the website is opened
  from your own computer, as Parts 13 and 16 show.
- `db\schema.sql` already contains the tables added in Parts 15 and 16. The upgrade files in `db\migrations`
  are safe to run on top of it.
- The Terraform code was written to take over a system that had first been built by hand (Parts 8 to 13).
  To build directly from the code instead, read Part 14, section 14.6, first.
- The region used throughout is `ap-south-1`. To use another one, change `region` in `variables.tf` and the
  region line near the top of each script.

## Cost
- Parts 1 to 7 run mostly on your computer and cost nothing or almost nothing.
- From Part 8 the system in AWS costs roughly USD 0.08 per hour while it is running (check current prices).
- Run `.\infra\scripts\pause.ps1` whenever you stop working, and `.\infra\scripts\resume.ps1` to continue.
- When you are finished for good, Part 14, section 14, removes everything.

## Keep it safe
- Never put a `.env` file, `demo.auto.tfvars` or `terraform.tfstate` into Git, email or chat.
  The `.gitignore` file in this package already excludes them.
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
