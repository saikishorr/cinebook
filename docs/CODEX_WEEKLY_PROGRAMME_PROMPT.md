# CineBook: weekly cinema programmes, like real Pune listings (backend work for Codex)

The hard rules in `docs/CODEX_BACKEND_PROMPT.md` still apply. In short:
- Do not touch `frontend/`.
- API changes are additive only.
- Use plain psycopg SQL; scripts must work in PowerShell 5.1.
- Tests must pass offline.

This round changes **only how demo shows are generated**. No API shape changes are needed, and the frontend
already shows whatever the API returns.

## The problem (verified in the developer's database on 2026-11-20)

`backend/app/programme.py` plans **each day independently**. It seeds every choice with `(cinema_id, day)`,
re-runs "two shows per film citywide" coverage every day, and picks a screen's primary film per day. So a film
appears at a cinema on one day, vanishes for two days, and comes back on another. For example, at
"Rajhans Cinemas, 93 Avenue Mall":

```
Aadi Anant          1 day : 21
Ebenezer            3 days: 23 24 27
Wildwood            2 days: 21 26
Ruff and Tuff Kanya 2 days: 25 26
(... 15 films, nearly all on a single day)
```
Citywide, **0 of 375** (cinema, film) pairs play on all 7+ days of the schedule. Real cinemas don't work like
this, and the listings on BookMyShow and District don't look like this.

## How real Indian cinema programming works (the behaviour to reproduce)

1. **The booking week runs Friday to Thursday.** New releases open on Friday.
2. Each cinema decides its **line-up for the week**: which films it carries and on which screens. A film
   carried that week plays **every day of the week**, normally at the **same times each day**.
3. Each screen has a **fixed daily timetable**. A popular film gets one or more screens to itself; smaller films
   **share a screen**, for example Audi 4: Marathi film at 10:00 and 16:30, Telugu film at 13:15 and 19:45, every
   day.
4. **Holdovers.** Next week, most films continue at the same cinema on the same screens, unless they are
   replaced by new releases.
5. **Weekends** may add one extra late show on a busy screen. Ticket prices already vary by weekday and evening
   (keep the current pricing rules).

## What to build

### 1. A weekly programme model
- `week_start(day)` → the Friday on or before `day`. A booking week is `week_start` through `week_start + 6`.
- **Plan a cinema for the whole week, then copy the plan onto each day.** Never choose films per day.
  - **Seeding:** `stable_seed(cinema_id, week_start)`. Never seed anything that picks films or times with
    `day`; seeding prices by `(screen, slot, day)` is fine.
  - **Which films a cinema carries:**
    - **Multiplexes:** roughly `screens + 2` films a week (minimum 3), weighted by the existing language weights,
      TMDB popularity order (the active `movies.id` order the importer creates) and release recency.
    - **Single screens:** 1 film, or 2 sharing the screen, mostly Marathi or Hindi.
    - **Lounge or all-recliner cinemas** (PVR Director's Cut, MovieMax Gold): the 3–5 most popular films.
  - **Screen allocation:** give the cinema's top film(s) a full screen each. Pair lower-ranked films on shared
    screens, at most 2 films per screen, alternating.
  - **Timetable per screen:** start at the opening time (keep the current 09:00–10:30 variation, seeded per
    `(cinema, week, screen)`). Each show is runtime + 20 minutes, rounded up to 5 minutes, and nothing starts
    after 23:15. This list of `(start time, film)` slots is **the same for every day of the week**. On Friday,
    Saturday and Sunday you may add one extra show to the end of a full-screen film's day if it still fits before
    23:15.
- **Citywide coverage, per week instead of per day:** every active film must be carried by **at least 2
  cinemas for the whole week**. Plan coverage before the weighted fill: give uncovered films a shared slot
  first, then allocate the rest.
- **Holdover continuity:** when planning a new week, start from last week's line-up at the same cinema (read it
  from the shows table). Keep films that are still active, on the same screens and times where possible, and
  replace only inactive films or the lowest-ranked ones to make room for films that are new to the cinema.
  Re-running the scheduler must give the same result.

### 2. Today and the days in the window
- The scheduler still covers `today .. today + 7` (8 days), which crosses into next week. Days in the current
  week use the current week's plan; days in the next week use next week's plan, built with holdover from this
  week.
- **Today:** create only the slots whose start time is still in the future.
- **Protected shows:** keep every show with bookings or live holds. Plan around them: a protected interval
  blocks its screen time. If a protected show's film is not in that screen's weekly plan, leave the show where it
  is and skip any planned slot that overlaps it.

### 3. Film changes during the week (`movie_ids` path used by the admin)
- **A film activated mid-week** joins the line-up **from that day until Thursday** at 2 or more cinemas. It takes
  over one alternating slot pattern on a shared screen, replacing the lowest-ranked film there, and **only unbooked,
  unheld** future shows are removed. From that day on it must play every remaining day of the week at the same
  times. Next week it is a normal holdover.
- **A film deactivated** loses its unbooked future shows (as now). Give its slots to the other film on the same
  screen, or else to the cinema's top film, using that film's timetable pattern.

### 4. A one-time rebuild of the existing per-day schedule
- Add `scripts/schedule_shows.py --rebuild`, with its PowerShell wrapper: delete **every unbooked, unheld
  future show** at active cinemas, then build the weekly programmes. Booked shows stay.
- `setup_local.py` and `import-movies.ps1` / `import-cinemas.ps1` keep calling the normal (non-rebuild) scheduler.
  It must be **idempotent**: a second run creates 0 shows and deletes 0 shows.

### 5. Keep everything else
Keep these exactly as they are now:
- pricing and recliner pricing, and the `prices()` and `recliner_price()` rules;
- the 23:15 last-start rule and the 20-minute turnaround;
- `ON CONFLICT (screen_id, start_time)`;
- the advisory lock;
- the demo wording.

## Acceptance checks (write these as tests on a fixture of about 6 cinemas and about 12 films, plus run them on the real database and report the numbers)
1. **Continuity:** for every (cinema, film) pair scheduled in a booking week, the film has shows on **every**
   day from its first day in that week through Thursday. On today, count only slots after `now`. The target is
   100%, apart from days where protected shows block every slot, which the test must list.
2. **Same times:** for a given screen in a given week, the set of `(time of day, film)` slots is identical on
   Monday to Thursday, and Friday to Sunday has the same set, possibly plus one extra late show.
3. **Week boundary:** Thursday's plan and the next Friday's plan may differ. At least 70% of a cinema's films
   carry over when no new films were activated.
4. **Coverage:** every active film is at 2 or more cinemas for every day of the window.
5. **Mid-week activation:** activating a film on a Tuesday gives it shows on Tuesday to Thursday at the same
   times each day, at 2 or more cinemas. Booked shows are untouched.
6. **Idempotent:** a second scheduler run creates 0 shows and deletes 0 shows.
7. **Determinism:** the same inputs give the same programme.
8. **The real data**, after `--rebuild`:
   - print, for "Rajhans Cinemas, 93 Avenue Mall", each film with its days and its daily times;
   - print the citywide share of (cinema, film) pairs that play on every remaining day of their week;
   - print the total number of shows.

## Report back with
1. Changed files.
2. The command to rebuild, which the developer will run once: `.\scripts\schedule-shows.ps1 -Rebuild`.
3. The pytest summary lines.
4. The numbers from acceptance check 8.
