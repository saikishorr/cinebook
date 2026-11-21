# CineBook - project journal

A plain-language history of the project: the steps, the decisions and the problems met.
Start with `START-HERE.md`.

## The idea
Build a movie ticket booking system ("CineBook") one step at a time, as a learning and training project.
- It will never go live to the public and must stay free to run.
- Every step is explained first (why, what happens, purpose, part of the architecture), then built, then reviewed.

## Working method that was agreed
- One step at a time: implement, review the output, then the next step.
- Python for the code; React for the website; PostgreSQL for the database.

## Phase 1 - the booking system
| Step | What was built |
|---|---|
| 1 | Workstation setup |
| 2 | PostgreSQL database: 8 tables, sample data, ER diagram |
| 3 | Backend API (FastAPI) |
| 4 | Seat holds (5-minute holds, so two customers can never book the same seat) |
| 5 | React website |
| 6 | Booking confirmation: a worker confirms the booking, releases the hold and sends the email |

Main decisions:
- The API stores holds in PostgreSQL (`seat_holds`, `seat_hold_seats`) with an expiry time.
- Confirmation runs in the API process right after the response, and is safe to repeat.
- Demo emails are written to `backend/outbox/` instead of being sent.

## Phase 2 - booking SMS with a chat link
Request: with the confirmation email, also send an SMS containing a link that brings the customer back to the website, to a chatbot.

Decisions:
- Real SMS in India needs DLT registration (business, sender name, templates). To avoid the regulation and paperwork for a training system, **no real SMS is sent**. The SMS is stored and shown in a "Demo Phone" inbox on the website.
- Only registered demo numbers can receive an SMS; the customer must tick a consent box.
- The chat link never expires (the first design had an expiry; it was removed on request). A single link can be switched off.

Steps:
| Step | What |
|---|---|
| 2.1 | Settings: demo numbers, site address, Demo Phone access code (`setup-demo-sms.ps1`) |
| 2.2 | Database migration 002: `bookings.sms_phone`, `sms_consent`; tables `chat_links`, `sms_messages` |
| 2.3 | API: phone handling, booking check, `GET /chat-links/{code}`, `POST /demo-phone/inbox`, rate limits |
| 2.4 | Worker: `demo_sms.py` creates the link and writes the SMS in a savepoint |
| 2.5 | Website: consent box, Demo Phone page, chat page |
| 2.6 | End-to-end test |

## Phase 3 - the chat assistant
Request: a chatbot that answers questions about the customer's booking and the information on the website, and politely refuses everything else.

Decisions:
- Model: Gemini API free tier.
- The model is given only three things: the one booking behind the link, the published movies and showtimes, and the Help text.
- The refusal is one fixed sentence shown by our code, not written by the model.
- The assistant is read-only: it cannot cancel, change or refund.

Steps:
| Step | What |
|---|---|
| 3.1 | Model connection check (`check-gemini.py`); design notes |
| 3.2 | Help and info content in one file, `GET /help`, Help page |
| 3.3 | Database migration 003: table `chat_messages` |
| 3.4 | Chat engine and endpoints (`chat_llm.py`, `chat_engine.py`, `routers/chat.py`) |
| 3.5 | Chat panel on the chat page |
| 3.6 | Evaluation with the real model: 39 questions in 8 groups, 39 of 39 passed |

## Phase 4 - real cinemas, accounts and the admin console
- 20 curated real Pune cinemas (OpenStreetMap as an optional source), with editable seat layouts.
- Weekly Friday-to-Thursday demo programmes and current films from TMDB.
- Customer accounts, a role-based admin console (Super admin, Manager, Support) and an audit log.

## Problems met and how they were solved
| Problem | Cause | Fix |
|---|---|---|
| Evaluation question about another booking failed | The model described the customer's own booking, then quoted its own rule | Clearer rule, worked examples, and a filter that blocks replies repeating the instructions |
| A booking stayed "pending" after a failed confirmation | The confirmation step raised an error | Stale pending bookings are marked failed and their seats freed at startup and on each new booking |
| Ports 5173 / 8000 already in use | An earlier session still running | Stop the process listening on the port |
