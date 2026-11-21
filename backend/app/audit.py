"""The admin audit log: one row for every change a staff member makes."""
import json
import logging

logger = logging.getLogger(__name__)


def record(connection, admin: dict, action: str, target_type: str | None = None, target_id=None, **details) -> None:
    """Write an audit row inside the caller's transaction, so the log and the change commit together."""
    connection.execute(
        """INSERT INTO admin_audit_log (admin_user_id, admin_username, action, target_type, target_id, details)
           VALUES (%s, %s, %s, %s, %s, %s::jsonb)""",
        (admin.get("id"), admin["username"], action, target_type,
         None if target_id is None else str(target_id), json.dumps(details, default=str)))
    logger.info("Admin action %s by %r on %s %s", action, admin["username"], target_type, target_id)
