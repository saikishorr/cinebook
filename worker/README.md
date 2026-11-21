# Booking confirmation worker

This module confirms pending bookings in PostgreSQL. For each booking it:

1. Locks the booking and marks it `CONFIRMED` with a simulated payment reference.
2. Writes the chat link and the demo SMS in the same transaction (`demo_sms.py`).
3. Releases the seat hold.
4. Sends the confirmation email.

The API loads these modules by path and runs the confirmation right after the HTTP response, so no
separate process is needed. The API also passes in its own seat-hold release and email functions,
and the email goes to `backend/outbox/`. Confirming the same booking twice is safe: the second run
is skipped, so nothing is charged twice and no duplicate SMS is written.

`confirm_booking.sweep_stale_pending(connection, older_than_minutes=10)` marks bookings stuck in
`PENDING` as `FAILED` and frees their seats. The API calls it at startup.

Run the tests from the project root: `.\.venv\Scripts\python -m pytest worker`.
