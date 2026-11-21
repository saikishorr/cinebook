"""One seat-type price rule for maps, holds and checkout."""
from decimal import Decimal, ROUND_HALF_UP


def recliner_price(premium):
    return (Decimal(premium) * Decimal("1.8") / 10).quantize(Decimal(1), rounding=ROUND_HALF_UP) * 10


def seat_price(show, seat_type):
    if seat_type == "RECLINER":
        value = show.get("recliner_price")
        value = value if value is not None else recliner_price(show["premium_price"])
    else:
        value = show["premium_price"] if seat_type == "PREMIUM" else show["regular_price"]
    return Decimal(value).quantize(Decimal("0.01"))


def seat_price_sql():
    return """CAST(CASE WHEN seat.seat_type = 'RECLINER'
                   THEN COALESCE(s.recliner_price, round(s.premium_price * 1.8 / 10) * 10)
                   WHEN seat.seat_type = 'PREMIUM' THEN s.premium_price ELSE s.regular_price END AS NUMERIC(10,2))"""
