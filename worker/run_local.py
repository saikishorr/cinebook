"""Poll the booking SQS queue and run the Lambda handler locally."""
import os
import logging

import boto3
from dotenv import load_dotenv


def main() -> None:
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    # Show the worker's INFO lines (e.g. "CONFIRMED ... - email sent - demo SMS written") in the terminal.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("botocore").setLevel(logging.WARNING)
    # Load settings before importing the module that creates its AWS clients.
    from confirm_booking import lambda_handler

    sqs = boto3.client("sqs", region_name=os.getenv("AWS_REGION"))
    queue_url = os.environ["BOOKING_QUEUE_URL"]
    print("Waiting for booking messages...", flush=True)
    try:
        while True:
            response = sqs.receive_message(
                QueueUrl=queue_url, WaitTimeSeconds=20, MaxNumberOfMessages=10
            )
            messages = response.get("Messages", [])
            if not messages:
                print("Waiting for booking messages...", flush=True)
                continue
            event = {
                "Records": [
                    {"messageId": message["MessageId"], "body": message["Body"]}
                    for message in messages
                ]
            }
            result = lambda_handler(event, None)
            failed = {item["itemIdentifier"] for item in result["batchItemFailures"]}
            for message in messages:
                if message["MessageId"] not in failed:
                    sqs.delete_message(
                        QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
                    )
    except KeyboardInterrupt:
        print("Stopping booking worker.", flush=True)


if __name__ == "__main__":
    main()
