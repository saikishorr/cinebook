"""Cloud interfaces stay lazy and retain existing FIFO message identifiers."""
import json
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from app import email, queue
from app.config import settings
from app.holds import dynamodb
from app.holds.base import SeatsUnavailable, StoreUnavailable


def test_sqs_lazy_and_payload(monkeypatch):
    calls, creations = [], []
    monkeypatch.setattr(settings, "queue_backend", "sqs")
    monkeypatch.setattr(settings, "booking_queue_url", "https://queue.test/bookings.fifo")
    monkeypatch.setattr(queue, "sqs", None)
    def client(service, **kwargs):
        creations.append(service)
        return SimpleNamespace(send_message=lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr("boto3.client", client)
    booking = {"booking_ref": "BKABC123", "booking_id": 1, "hold_id": "hold", "show_id": 2}
    assert not creations
    queue.send_booking_message(booking)
    queue.send_booking_message(booking)
    assert creations == ["sqs"]
    assert json.loads(calls[0]["MessageBody"]) == booking
    assert calls[0]["MessageGroupId"] == "show-2"
    assert calls[0]["MessageDeduplicationId"] == "BKABC123"


def test_cloud_cancellation_uses_existing_worker_configuration(monkeypatch):
    calls = []
    monkeypatch.setattr(settings, "queue_backend", "sqs")
    monkeypatch.setattr(settings, "email_backend", "ses")
    monkeypatch.setattr(settings, "ses_sender_email", "")
    monkeypatch.setattr(queue, "sqs", SimpleNamespace(send_message=lambda **kwargs: calls.append(kwargs)))
    booking = {"booking_ref": "BKABC123", "show_id": 2, "email": "test@example.com", "refund_ref": "SIMREF-123"}
    email.send_cancellation(booking)
    message = json.loads(calls[0]["MessageBody"])
    assert message["action"] == "CANCELLED" and message["booking"]["refund_ref"] == "SIMREF-123"
    assert calls[0]["MessageDeduplicationId"] == "cancel-BKABC123"


def test_dynamo_lazy_clients_and_domain_errors(monkeypatch):
    creations = []
    monkeypatch.setattr(dynamodb, "dynamodb_client", None)
    monkeypatch.setattr(dynamodb, "table", None)
    def conflict(**kwargs):
        raise ClientError({"Error": {"Code": "TransactionCanceledException"},
                           "CancellationReasons": [{"Code": "ConditionalCheckFailed"}]}, "TransactWriteItems")
    def client(service, **kwargs):
        creations.append(service)
        return SimpleNamespace(transact_write_items=conflict)
    monkeypatch.setattr(dynamodb, "client", client)
    monkeypatch.setattr(dynamodb, "resource", lambda *args, **kwargs: SimpleNamespace(Table=lambda name: object()))
    assert creations == []
    with pytest.raises(SeatsUnavailable):
        dynamodb.create_hold("hold", 1, [1], 9999999999, 1)
    assert creations == ["dynamodb"]
    def unavailable(**kwargs):
        raise ClientError({"Error": {"Code": "AccessDeniedException"}}, "TransactWriteItems")
    monkeypatch.setattr(dynamodb.dynamodb_client, "transact_write_items", unavailable)
    with pytest.raises(StoreUnavailable):
        dynamodb.create_hold("hold", 1, [1], 9999999999, 1)
