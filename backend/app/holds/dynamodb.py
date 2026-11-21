"""Small DynamoDB wrapper for temporary seat holds."""
from datetime import datetime, timezone
from functools import wraps
from app.holds.base import SeatsUnavailable, StoreUnavailable
from boto3 import client, resource
from boto3.dynamodb.types import TypeSerializer
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from app.config import settings

# Reuse the AWS connections for the life of this Python process.
dynamodb_config = Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 2})
dynamodb_client = None
table = None


def _operation(function):
    @wraps(function)
    def call(*args, **kwargs):
        global dynamodb_client, table
        try:
            if dynamodb_client is None:
                dynamodb_client = client("dynamodb", region_name=settings.aws_region, config=dynamodb_config)
            if table is None:
                table = resource("dynamodb", region_name=settings.aws_region, config=dynamodb_config).Table(settings.dynamodb_table)
            return function(*args, **kwargs)
        except ClientError as error:
            if is_condition_failure(error):
                raise SeatsUnavailable from error
            raise StoreUnavailable from error
        except BotoCoreError as error:
            raise StoreUnavailable from error
    return call


_serializer = TypeSerializer()


def _item(values: dict) -> dict:
    return {key: _serializer.serialize(value) for key, value in values.items()}


@_operation
def create_hold(hold_id: str, show_id: int, seat_ids: list[int], expires_at: int, created_at: int) -> None:
    """Claim all seats and store their shared hold record atomically."""
    now = int(datetime.now(timezone.utc).timestamp()) + 1
    requests = []
    for seat_id in seat_ids:
        requests.append({"Put": {
            "TableName": settings.dynamodb_table,
            "Item": _item({"pk": f"SHOW#{show_id}", "sk": f"SEAT#{seat_id}", "hold_id": hold_id, "expires_at": expires_at}),
            "ConditionExpression": "attribute_not_exists(pk) OR expires_at < :now",
            "ExpressionAttributeValues": {":now": _serializer.serialize(now)},
        }})
    requests.append({"Put": {
        "TableName": settings.dynamodb_table,
        "Item": _item({"pk": f"HOLD#{hold_id}", "sk": "META", "show_id": show_id,
                        "seat_ids": seat_ids, "expires_at": expires_at, "created_at": created_at}),
        "ConditionExpression": "attribute_not_exists(pk)",
    }})
    dynamodb_client.transact_write_items(TransactItems=requests)


@_operation
def get_hold(hold_id: str) -> dict | None:
    try:
        response = table.get_item(Key={"pk": f"HOLD#{hold_id}", "sk": "META"}, ConsistentRead=True)
        return response.get("Item")
    except (BotoCoreError, ClientError) as error:
        raise StoreUnavailable from error


@_operation
def claim_hold(hold_id: str, booking_ref: str) -> tuple[str, str | None]:
    """Lock a live hold to one booking before writing anything to PostgreSQL."""
    try:
        dynamodb_client.update_item(
            TableName=settings.dynamodb_table,
            Key=_item({"pk": f"HOLD#{hold_id}", "sk": "META"}),
            UpdateExpression="SET booking_ref = :booking_ref",
            ConditionExpression="attribute_exists(pk) AND attribute_not_exists(booking_ref) AND expires_at > :now",
            ExpressionAttributeValues={":booking_ref": _serializer.serialize(booking_ref),
                                       ":now": _serializer.serialize(int(datetime.now(timezone.utc).timestamp()))},
        )
        return "CLAIMED", None
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise StoreUnavailable from error
        try:
            item = get_hold(hold_id)
        except StoreUnavailable:
            raise
        if item and item.get("booking_ref"):
            return "ALREADY_CLAIMED", item["booking_ref"]
        return "EXPIRED_OR_MISSING", None
    except BotoCoreError as error:
        raise StoreUnavailable from error


@_operation
def unclaim_hold(hold_id: str, booking_ref: str) -> None:
    """Release a claim only when it still belongs to this failed booking attempt."""
    try:
        dynamodb_client.update_item(
            TableName=settings.dynamodb_table,
            Key=_item({"pk": f"HOLD#{hold_id}", "sk": "META"}),
            UpdateExpression="REMOVE booking_ref",
            ConditionExpression="booking_ref = :booking_ref",
            ExpressionAttributeValues={":booking_ref": _serializer.serialize(booking_ref)},
        )
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise StoreUnavailable from error
    except BotoCoreError as error:
        raise StoreUnavailable from error


@_operation
def get_show_holds(show_id: int) -> list[dict]:
    """Read all current and expired hold rows for a show; callers check TTL themselves."""
    rows = []
    response = table.query(KeyConditionExpression="#pk = :pk", ExpressionAttributeNames={"#pk": "pk"},
                           ExpressionAttributeValues={":pk": f"SHOW#{show_id}"}, ConsistentRead=True)
    rows.extend(response.get("Items", []))
    while response.get("LastEvaluatedKey"):
        response = table.query(KeyConditionExpression="#pk = :pk", ExpressionAttributeNames={"#pk": "pk"},
                               ExpressionAttributeValues={":pk": f"SHOW#{show_id}"}, ConsistentRead=True,
                               ExclusiveStartKey=response["LastEvaluatedKey"])
        rows.extend(response.get("Items", []))
    return rows


@_operation
def release_hold(hold_id: str, show_id: int, seat_ids: list[int]) -> None:
    """Delete matching seat rows, then remove the hold record."""
    for seat_id in seat_ids:
        try:
            dynamodb_client.delete_item(
                TableName=settings.dynamodb_table,
                Key=_item({"pk": f"SHOW#{show_id}", "sk": f"SEAT#{seat_id}"}),
                ConditionExpression="hold_id = :hold_id",
                ExpressionAttributeValues={":hold_id": _serializer.serialize(hold_id)},
            )
        except ClientError as error:
            # A later hold may already own this seat, so leave that row alone.
            if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
    dynamodb_client.delete_item(
        TableName=settings.dynamodb_table,
        Key=_item({"pk": f"HOLD#{hold_id}", "sk": "META"}),
    )


def is_condition_failure(error: ClientError) -> bool:
    reasons = error.response.get("CancellationReasons", [])
    return any(reason.get("Code") == "ConditionalCheckFailed" for reason in reasons)


def held_seat_ids(show_id: int) -> set[int]:
    now = int(datetime.now(timezone.utc).timestamp())
    return {int(item["sk"].split("#", 1)[1]) for item in get_show_holds(show_id)
            if int(item["expires_at"]) > now}
