"""The assistant has bounded, local venue context and cannot invent facilities."""
import psycopg
from psycopg.rows import dict_row

from app.chat_engine import INSTRUCTIONS, MAX_PROMPT_BYTES, build_context, build_system_prompt
from app.help_info import help_as_text
from tests.test_cinemas_api import catalogue as catalogue


def test_context_booking_cinema_three_dates_and_budget(catalogue, database_url):
    c = catalogue
    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as conn:
        customer = conn.execute("INSERT INTO customers (full_name,email) VALUES ('Chat Budget Test',%s) RETURNING id",
                                (f"chat-{c['tag']}@example.com",)).fetchone()["id"]
        booking = conn.execute("""INSERT INTO bookings (booking_ref,customer_id,show_id,status,total_amount)
                                  VALUES (%s,%s,%s,'CONFIRMED',220) RETURNING id""",
                               ("CHAT" + c["tag"],customer,c["shows"][1])).fetchone()["id"]
        try:
            context = build_context(conn.cursor(), booking)
            assert "A Cinema " + c["tag"] in context
            assert "Area " + c["tag"] in context and "Address " + c["tag"] in context
            assert "DEMO TICKET - not valid for entry" in context
            assert "CINEMAS (names and areas only)" in context
            local_shows = context.split("SHOWTIMES at the booking's cinema:",1)[1].split("HELP AND INFO")[0]
            assert "2:00 PM" in local_shows and "11:00 AM" in local_shows
            assert "10:00 AM" not in local_shows  # that screening belongs to the other cinema
            assert "@example.com" not in context and "Budget Test" not in context
            assert len(build_system_prompt(context).encode()) <= MAX_PROMPT_BYTES
        finally:
            conn.execute("DELETE FROM bookings WHERE id = %s", (booking,))
            conn.execute("DELETE FROM customers WHERE id = %s", (customer,))


def test_facilities_are_unknown_demo_notice_and_read_only():
    text = help_as_text()
    assert "not affiliated" in text and "not valid for entry" in text and "simulated" in text
    assert "vary by cinema" in text and "no customer contact" in text
    assert "cannot cancel" in text and "2 hours" in text
    assert "Never invent facilities" in INSTRUCTIONS
    assert "cannot cancel, change or refund" in INSTRUCTIONS
