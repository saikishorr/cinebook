"""One SQL expression shared by show lists and the assistant."""

def availability_columns() -> str:
    booked = """SELECT bs.seat_id FROM booking_seats bs JOIN bookings b ON b.id = bs.booking_id
                WHERE bs.show_id = s.id AND b.status IN ('PENDING', 'CONFIRMED')"""
    occupied = booked + " UNION SELECT seat_id FROM seat_hold_seats WHERE show_id = s.id AND expires_at > now()"
    return f"""(SELECT count(*) FROM seats WHERE screen_id = s.screen_id) AS seats_total,
               (SELECT count(*) FROM seats WHERE screen_id = s.screen_id
                AND id NOT IN ({occupied})) AS seats_available"""
