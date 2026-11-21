# CineBook: backend work for Codex

You are working on **CineBook**, a movie-ticket booking system used for training. The repository is a working
FastAPI + PostgreSQL backend (`backend/`), a booking-confirmation worker that runs as AWS Lambda or locally
(`worker/`), SQL schema/migrations (`db/`), a React frontend (`frontend/`) and AWS infrastructure (`infra/`).
Read `START-HERE.md`, `docs/PROJECT-JOURNAL.md`, every file in `backend/app/`, `worker/` and `db/`, and the
backend tests before changing anything.

You own the **backend, worker, database and local dev scripts**. Another engineer owns the frontend in
parallel and will build against the API contract in Part C, so implement that contract exactly.

---

## Hard rules

1. **Do not modify anything in `frontend/`.**
2. **Do not remove or rename any existing API path, request field or response field.** Only add. The frontend
   in production depends on every existing field.
3. **The AWS deployment must keep working with no configuration change.** Every new setting defaults to the
   current cloud behaviour (DynamoDB, SQS, SES). Check `infra/ec2/api-user-data.sh`, `infra/terraform/*.tf` and
   `infra/lambda/build.ps1` to confirm which environment variables the cloud sets and which files the Lambda
   zip contains.
4. No new heavy dependencies: no ORM, no Alembic, no Redis. Use psycopg 3 and plain SQL, as the code does now.
5. Keep the existing style: small modules, plain-English comments that explain *why*, parameterised SQL only.
6. Every schema change is a numbered migration in `db/migrations/` with a matching `_down.sql`, **and** is
   appended to `db/schema.sql` (which must stay a one-shot fresh install). Follow the 002 and 003 pattern.
7. Scripts must run in **Windows PowerShell 5.1** (no `&&`, no ternary). The developer machine has Python 3.12,
   Node 24 and PostgreSQL 18 and **no AWS CLI, no AWS credentials and no Docker**.
8. Never write secrets into tracked files. `backend/.env` and `worker/.env` are created by the developer.
9. All tests must pass with **no network and no AWS credentials**.

---

## Part A (P0): local mode, so the full booking flow runs with no AWS

Today a seat hold needs DynamoDB, a booking needs SQS, and confirmation needs the worker plus SES. On a laptop
with no AWS, the flow stops at "Hold seats" with a 503. Make the whole flow (browse → hold → book → confirmed
→ demo SMS → chat page) work locally with only PostgreSQL.

### A1. Settings (`backend/app/config.py`)
- `holds_backend: Literal["dynamodb", "postgres"] = "dynamodb"`
- `queue_backend: Literal["sqs", "inline"] = "sqs"`
- `email_backend: Literal["ses", "log"] = "ses"` (used by the confirmation logic in inline mode)
- `booking_queue_url` becomes optional (`""`), and is **required only when `queue_backend == "sqs"`**. Raise a
  clear validation error at startup otherwise.
- Update `backend/.env.example` with a commented **"Local mode (no AWS)"** block:
  `HOLDS_BACKEND=postgres`, `QUEUE_BACKEND=inline`, `EMAIL_BACKEND=log`, and `CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`.

### A2. Hold store abstraction
- Create a package `backend/app/holds/` with:
  - `base.py`: a `HoldStore` `Protocol` with `create_hold`, `get_hold`, `claim_hold`, `unclaim_hold`,
    `release_hold` and `held_seat_ids(show_id) -> set[int]` (already filtered to unexpired holds). It also defines
    the domain exceptions `SeatsUnavailable` and `StoreUnavailable`.
  - `dynamodb.py`: the current `holds_store.py` logic moved here, unchanged in behaviour. Create the boto3
    clients **lazily** (on first use), not at import time.
  - `postgres.py`: a new implementation (see A3).
  - `__init__.py`: `get_hold_store()`, which picks the implementation from `settings.holds_backend`.
- Routers (`holds.py`, `bookings.py`, `shows.py`) use only the protocol and the domain exceptions. **No botocore
  import may remain in any router.** Keep `app/holds_store.py` as a thin re-export only if tests import it;
  otherwise delete it and update the tests.

### A3. PostgreSQL hold store, migration `004_seat_holds.sql`
```sql
CREATE TABLE seat_holds (
  hold_id     TEXT PRIMARY KEY,
  show_id     BIGINT NOT NULL REFERENCES shows(id),
  seat_ids    BIGINT[] NOT NULL,
  expires_at  TIMESTAMPTZ NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  booking_ref TEXT                     -- set by claim_hold
);
CREATE TABLE seat_hold_seats (
  show_id    BIGINT NOT NULL,
  seat_id    BIGINT NOT NULL REFERENCES seats(id),
  hold_id    TEXT NOT NULL REFERENCES seat_holds(hold_id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (show_id, seat_id)       -- one live hold per seat per show
);
CREATE INDEX idx_seat_holds_expires ON seat_holds (expires_at);
```
- `create_hold` runs in **one transaction**: delete *expired* rows for those seats, insert the hold, then insert
  the seat rows with `ON CONFLICT DO NOTHING RETURNING seat_id`. If fewer rows came back than seats requested,
  roll back and raise `SeatsUnavailable` (the router returns 409, as now).
- `claim_hold` / `unclaim_hold` must keep the exact semantics of the DynamoDB versions: a conditional
  `UPDATE ... WHERE booking_ref IS NULL AND expires_at > now()`, returning `CLAIMED`, `ALREADY_CLAIMED` (plus the
  existing ref) or `EXPIRED_OR_MISSING`.
- The hold store must use its **own short autocommit statements or its own pooled connection**, never the
  request's booking transaction. Claim-before-insert ordering in `create_booking` must not change.
- Expired rows are cleaned up opportunistically (for example, inside `create_hold`). No cron is needed.

### A4. Inline queue and confirmation
- Add a queue abstraction in `backend/app/queue.py`: `send_booking_message(booking)` dispatches to SQS (current
  code, client created lazily) or **inline**.
- In inline mode, `create_booking` still commits the booking as `PENDING` and returns 202. Confirmation then
  runs **after the response**, through FastAPI `BackgroundTasks`, so the frontend still sees PENDING change to
  CONFIRMED.
- **Do not duplicate the confirmation SQL.** Refactor `worker/confirm_booking.py` so that `_process_record`
  receives its side effects as parameters: `release_hold(hold_id, show_id, seat_ids)` and
  `send_email(booking, seats)`. The defaults keep today's boto3 behaviour, so the Lambda handler is unchanged.
  Make the module's boto3 clients lazy: `boto3.client("dynamodb", region_name=None)` raises `NoRegionError`
  at import on a machine with no AWS config.
- In inline mode the API loads `worker/confirm_booking.py` and `worker/demo_sms.py` by path (`importlib`). This is
  for local development only and must never be needed in the Docker image. It passes the Postgres hold store's
  release function and a log email sender. The log sender writes the email to the log and saves an `.eml` file
  to `backend/outbox/`, which must be gitignored.
- Inline confirmation errors must be logged and must not crash the server. A failed confirmation leaves the
  booking `PENDING`, the same as a stuck queue message.

### A5. One-command local setup and run
- `scripts/setup-local.ps1`:
  1. Reads `DATABASE_URL` from `backend/.env` (it fails with a helpful message if the file is missing).
  2. Creates the `moviebooking` database if it is missing.
  3. On an **empty** database, applies `db/schema.sql`. On an existing one it **never runs schema.sql**, because
     the file starts with `DROP TABLE`. Instead it applies any migration not yet recorded in a new
     `schema_migrations(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ)` table. A `-Reset` switch drops and
     recreates the schema, after a confirmation prompt.
  4. Runs `db/seed.sql` and then `db/add_upcoming_shows.sql`, so there are shows **today** as well.
  5. Creates `worker/.env` from `backend/.env` values if it is missing.
- `scripts/run-local.ps1` starts the API (`.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000`
  from `backend/`) and the frontend (`npm run dev` in `frontend/`) in two new PowerShell windows.
- Add a short **"Run locally without AWS"** section to `START-HERE.md`.
- `GET /health` reports `{"status","database","holds_backend","queue_backend"}`. Adding these fields is allowed.

---

## Part B (P0): bugs found in review. Fix each one and add a regression test.

1. **The booking reference retry loses its claim** (`backend/app/routers/bookings.py`, the `for attempt in
   range(3)` loop). On a `bookings_booking_ref_key` collision, the code claims the hold with a new ref and
   `continue`s. The next iteration then runs `booking_ref = _new_booking_ref()` again, so the booking is inserted
   under a ref that is **not** the claimed one. Generate a new ref in exactly one place.
2. **The worker does not normalise demo numbers** (`worker/demo_sms.py`, `_allowed_numbers`). The API stores
   `+919800000000`, but if `SMS_DEMO_NUMBERS=9800000000` the worker's set holds `9800000000`, so it silently
   skips the SMS. Normalise with the same rules as `backend/app/phone.py`. The worker is packaged separately, so
   copy the small function and add a test asserting that both implementations agree.
3. **CORS**: `allow_credentials=True` combined with `allow_origins=["*"]` lets any site make credentialed calls.
   The API uses no cookies, so set `allow_credentials=False`.
4. **Booking lookup leaks contact details**: `GET /bookings/{ref}` returns the full email and phone to anyone
   holding a 6-character ref, with no rate limit. Add the masked fields from Part C and a per-IP limit of 30
   requests a minute, using the existing `SlidingWindowLimiter`. Keep the raw fields for now (see rule 2).
5. **Application INFO logs are dropped**: nothing configures logging, so `logger.info(...)` in `chat.py` never
   appears. Configure logging once at startup (level from `LOG_LEVEL`, default INFO). Add a request-id
   middleware that sets an `X-Request-ID` response header and includes the id in log lines.
6. **Inconsistent time zones**: `GET /movies/{id}/shows` returns `start_time` in UTC, while every other endpoint
   converts to `APP_TIMEZONE`. Convert it too.
7. **Customer overwrite**: `INSERT INTO customers ... ON CONFLICT (email) DO UPDATE SET full_name, phone` lets
   anyone rename another person's customer record by booking with that person's email. Store the name and phone
   on the **booking** (new nullable columns `customer_name` and `customer_phone`, filled on every new booking).
   Read them back with `COALESCE` to the customer row for old bookings. Stop overwriting `full_name` on conflict.
8. **The chat assistant ignores held seats**: in `chat_engine.build_context`, the `seats_free` query ignores held
   seats. Reuse the availability calculation from C3 so the chat and the website agree.
9. **Dependencies are unpinned**: `requirements.txt` has no versions. Pin exact versions that work on Python 3.12
   and 3.13, and keep `requirements-dev.txt` referencing it.

---

## Part C (P1): new API contract. The frontend is being built against this now.

All additions are **additive**. Field names and types are exact. Times are ISO 8601 with offset, in
`APP_TIMEZONE`, as the existing endpoints return them.

### C1. `GET /movies/{movie_id}` → `Movie`
Returns 404 `{"detail": "Movie {id} not found"}` for an unknown or inactive movie.

### C2. Richer `Movie` (migration `005_movie_details.sql`)
Add to the table, the model and every movie response:
```jsonc
"genres":       ["Drama", "Mystery"],   // TEXT[] NOT NULL DEFAULT '{}'
"backdrop_url": null,                    // TEXT, nullable
"trailer_url":  null,                    // TEXT, nullable (YouTube or mp4 link)
"release_date": "2026-10-03"             // DATE, nullable
```
Update `db/seed.sql` so the three sample films have genres and release dates. Leave the URLs null.

### C3. Seat availability on show lists
Add to `ShowSummary`, and so to `GET /movies/{id}/shows`, `GET /shows?date=` and `GET /shows/{id}`:
```jsonc
"seats_total": 96,
"seats_available": 71    // total - booked (PENDING or CONFIRMED) - currently held
```
Compute it in **one query per list**, not one query per show. In DynamoDB mode, count only booked seats and say
so in a code comment.

### C4. More detail on `BookingDetails` (`GET /bookings/{ref}`)
```jsonc
"email_masked":      "r***@gmail.com",   // first letter, ***, then the domain
"phone_masked":      "+91 ******5678",   // null if there is no phone; reuse mask_phone
"movie_language":    "Hindi",
"duration_minutes":  142,
"cancellable":       true,               // CONFIRMED and now < start_time - cutoff
"cancel_deadline":   "2026-11-21T16:00:00+05:30",  // start_time - cutoff; null when not CONFIRMED
"cancelled_at":      null,
"refund_ref":        null
```

### C5. `POST /bookings/{ref}/cancel` with body `{"email": "..."}` → `BookingDetails`
- New setting `cancel_cutoff_minutes: int = 120` (matches the Help text: up to 2 hours before the show).
- 404 `{"detail": "Booking not found"}` when the ref is unknown **or** the email does not match, compared
  case-insensitively. Return the same response in both cases so the endpoint cannot be used to check emails.
- 409 `{"detail": "Only confirmed bookings can be cancelled"}` for any status other than CONFIRMED.
- 409 `{"detail": "Bookings can only be cancelled up to 2 hours before the show"}` after the cutoff. Build the
  message from the setting.
- On success, in **one transaction**: set `status='CANCELLED'`, `cancelled_at=now()` and
  `refund_ref='SIMREF-'+hex`, then **delete the booking's `booking_seats` rows** so the seats can be sold again.
  Then send a cancellation email through the configured email backend. An email failure is logged and does not
  roll back the cancellation.
- Rate limit: 10 attempts per 15 minutes per IP, using `SlidingWindowLimiter`, as `demo_phone.py` does.
- Migration `006_booking_cancellation.sql` adds `cancelled_at TIMESTAMPTZ` and `refund_ref TEXT` to `bookings`,
  plus the `customer_name` and `customer_phone` columns from B7 if you put them here.
- **Update `backend/app/content/help_info.json`**: bookings can now be cancelled online on the booking page up to
  2 hours before the show, and at the box office. The chat assistant answers from this file. The assistant itself
  must still **not** be able to cancel anything. Make sure the existing chat tests and `backend/eval/` still pass
  against the new text.

### C6. Stale PENDING sweeper
Add `sweep_stale_pending(connection, older_than_minutes=10)`. It marks old PENDING bookings `FAILED` and deletes
their `booking_seats`, so seats stuck behind a lost queue message become free. In inline mode, call it on
startup and on each new booking. In the cloud, expose it from the worker module so a scheduled Lambda can call it
later. Do not add the schedule to Terraform.

---

## Part D (P2): quality. Do it if time allows, after A to C pass.

- `ruff` configuration in `backend/pyproject.toml` (or `ruff.toml`) and a clean run across `backend/` and `worker/`.
- A GitHub Actions workflow `.github/workflows/ci.yml` that runs the backend and worker tests against a
  `postgres:16` service with `HOLDS_BACKEND=postgres` and `QUEUE_BACKEND=inline`, plus `npm ci`, `npm run lint`
  and `npm run build` in `frontend/`.
- The rate limiters live in process memory, and the Dockerfile runs `--workers 2`, so each limit is effectively
  doubled. Leave a clear comment and an `API_WORKERS` setting. Do not add Redis.

---

## Tests (required)

The existing tests run against the developer's local PostgreSQL from `backend/.env` and skip when it is
unreachable. Keep that behaviour. Add these tests:
- Postgres hold store: two concurrent `create_hold` calls on an overlapping seat give exactly one success and
  one `SeatsUnavailable`. Also cover the claim, unclaim and release semantics and the reuse of an expired hold.
- End to end in local mode: `POST /shows/{id}/holds` → `POST /bookings` (with SMS consent and a demo number) →
  `GET /bookings/{ref}` reaches `CONFIRMED` → an `sms_messages` row and a `chat_links` row exist.
- Each Part B bug fix.
- Every Part C endpoint and field, including all error cases and their exact `detail` strings, and the fact
  that cancelled seats become `AVAILABLE` again in `GET /shows/{id}/seats`.
- Worker tests in `worker/tests/` still pass, including with injected `release_hold` and `send_email`.

Run `.venv\Scripts\python -m pytest backend` and `.venv\Scripts\python -m pytest worker` from the repository
root, or as the `pytest.ini` files expect, and report the results.

---

## When you finish, report back with

1. A list of changed and added files, grouped by Part.
2. The exact commands to set up and run locally from scratch.
3. Test results, pasted as the pytest summary lines.
4. **Any deviation from the Part C contract**, so the frontend can adapt. Ideally there is none.
5. Anything you found but did not fix.
