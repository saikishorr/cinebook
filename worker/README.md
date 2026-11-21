# Booking confirmation worker

This worker consumes booking messages from SQS, confirms pending bookings in PostgreSQL, releases matching seat holds in DynamoDB, and sends confirmation emails through SES v2. It safely handles duplicate SQS deliveries.

To run locally, copy `.env.example` to `.env`, fill in your settings, activate the project virtual environment, and run `python worker/run_local.py` from the project root. The worker will later be deployed to AWS Lambda with an SQS trigger.

For development without AWS, use `scripts/setup-local.ps1` and `scripts/run-local.ps1` instead.
The API loads these worker modules by path in inline mode, injects PostgreSQL hold release and log
email delivery, and runs confirmation after the HTTP response. No separate worker process is needed.
Cloud cancellation emails use the existing SQS queue and this worker's existing SES configuration.

`confirm_booking.sweep_stale_pending(connection, older_than_minutes=10)` is available for a future
scheduled Lambda. No cloud schedule is installed. Confirmation locks the booking so sweeping,
cancellation and duplicate deliveries cannot process it concurrently.
