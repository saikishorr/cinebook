"""Phase 3: the chat assistant's endpoints, reached from the chat page (/c/<code>).

GET  /chat-links/{code}/messages  - the saved conversation for this chat link
POST /chat-links/{code}/messages  - send a question, get the assistant's reply
"""
import logging
import re
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg import Connection

from app import chat_llm
from app.chat_engine import ERROR_TEXT, build_context, build_system_prompt, history_for_model, parse_reply
from app.config import settings
from app.db import get_connection
from app.models import ChatHistory, ChatSendRequest, ChatSendResponse
from app.ratelimit import SlidingWindowLimiter, client_key

router = APIRouter(prefix="/chat-links", tags=["chat assistant"])
logger = logging.getLogger(__name__)

_CODE = re.compile(r"[A-Za-z0-9]{10}")
# Per visitor: stops a script hammering the endpoint. The per-link hourly limit is checked in the database.
limiter = SlidingWindowLimiter(limit=20, window_seconds=60)
_COLUMNS = "id, role, content, outcome, created_at"


def _link(cursor, code: str) -> dict:
    if not _CODE.fullmatch(code):
        raise HTTPException(status_code=404, detail="This chat link is not valid")
    cursor.execute("SELECT id, booking_id, revoked_at FROM chat_links WHERE code = %s", (code,))
    link = cursor.fetchone()
    if link is None:
        raise HTTPException(status_code=404, detail="This chat link is not valid")
    if link["revoked_at"] is not None:
        raise HTTPException(status_code=410, detail="This chat link has been switched off")
    return link


def _remaining(cursor, link_id: int) -> int:
    cursor.execute("""SELECT count(*) AS used FROM chat_messages
                      WHERE chat_link_id = %s AND role = 'user' AND created_at > now() - interval '1 hour'""",
                   (link_id,))
    return max(0, settings.chat_messages_per_hour - cursor.fetchone()["used"])


def _local(rows: list[dict]) -> list[dict]:
    zone = ZoneInfo(settings.app_timezone)
    for row in rows:
        row["created_at"] = row["created_at"].astimezone(zone)
    return rows


@router.get("/{code}/messages", response_model=ChatHistory)
def read_messages(code: str, request: Request, connection: Connection = Depends(get_connection)):
    if not limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.")
    with connection.cursor() as cursor:
        link = _link(cursor, code)
        cursor.execute(f"SELECT {_COLUMNS} FROM chat_messages WHERE chat_link_id = %s ORDER BY id DESC LIMIT 100",
                       (link["id"],))
        rows = list(reversed(cursor.fetchall()))
        remaining = _remaining(cursor, link["id"])
    return {"enabled": chat_llm.is_configured(), "messages": _local(rows), "remaining_this_hour": remaining,
            "max_message_chars": settings.chat_max_message_chars}


@router.post("/{code}/messages", response_model=ChatSendResponse)
def send_message(code: str, body: ChatSendRequest, request: Request,
                 connection: Connection = Depends(get_connection)):
    if not limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.")
    if not chat_llm.is_configured():
        raise HTTPException(status_code=503, detail="The chat assistant is not available right now")
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Type a question first")
    if len(message) > settings.chat_max_message_chars:
        raise HTTPException(status_code=422,
                            detail=f"Please keep your message under {settings.chat_max_message_chars} characters")

    # 1. Save the question and collect what the model needs, in one transaction.
    with connection.transaction():
        with connection.cursor() as cursor:
            link = _link(cursor, code)
            if _remaining(cursor, link["id"]) <= 0:
                raise HTTPException(status_code=429,
                                    detail="You've reached the message limit for now. Please try again in a while.")
            cursor.execute(f"SELECT {_COLUMNS} FROM chat_messages WHERE chat_link_id = %s ORDER BY id DESC LIMIT 40",
                           (link["id"],))
            earlier = list(reversed(cursor.fetchall()))
            cursor.execute(f"""INSERT INTO chat_messages (chat_link_id, role, content) VALUES (%s, 'user', %s)
                               RETURNING {_COLUMNS}""", (link["id"], message))
            user_row = cursor.fetchone()
            system = build_system_prompt(build_context(cursor, link["booking_id"]))

    # 2. Ask the model (no database transaction is held open while waiting).
    turns = history_for_model(earlier, settings.chat_history_turns) + [{"role": "user", "content": message}]
    model = input_tokens = output_tokens = None
    try:
        result = chat_llm.generate(system, turns)
        outcome, text = parse_reply(result.text)
        model, input_tokens, output_tokens = result.model, result.input_tokens, result.output_tokens
    except chat_llm.LlmError as error:
        logger.warning("Chat model call failed for link %s: %s", link["id"], error)
        outcome, text = "ERROR", ERROR_TEXT

    # 3. Save the reply.
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(f"""INSERT INTO chat_messages (chat_link_id, role, content, outcome, model,
                                                          input_tokens, output_tokens)
                               VALUES (%s, 'assistant', %s, %s, %s, %s, %s) RETURNING {_COLUMNS}""",
                           (link["id"], text, outcome, model, input_tokens, output_tokens))
            reply_row = cursor.fetchone()
            remaining = _remaining(cursor, link["id"])
    logger.info("Chat link %s: %s (%s tokens in, %s out)", link["id"], outcome, input_tokens, output_tokens)
    return {"user_message": _local([user_row])[0], "reply": _local([reply_row])[0], "remaining_this_hour": remaining}
