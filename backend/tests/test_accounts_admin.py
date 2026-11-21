"""Customer accounts (sign-in to book) and the role-based admin console, against the local PostgreSQL."""
import secrets
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from psycopg.rows import dict_row

from app.admin_auth import hash_password
from app.config import settings
from app.routers import admin as admin_routes, auth as auth_routes

PASSWORD = "Test password 123"


@pytest.fixture
def env(client, database_url, monkeypatch):
    """A future show, three staff accounts (one per role), and clean-up of everything the test creates."""
    monkeypatch.setattr(settings, "require_login_for_booking", True)
    auth_routes.signups.reset()
    auth_routes.login_failures.reset()
    admin_routes.login_failures.reset()
    tag = secrets.token_hex(4)
    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as conn:
        screen = conn.execute("""SELECT sc.id FROM screens sc JOIN cinemas ci ON ci.id = sc.cinema_id
                                 WHERE ci.is_active ORDER BY sc.id LIMIT 1""").fetchone()["id"]
        movie = conn.execute("SELECT id FROM movies WHERE is_active ORDER BY id LIMIT 1").fetchone()["id"]
        start = datetime.now(timezone.utc) + timedelta(days=4, microseconds=secrets.randbelow(10 ** 6))
        show_id = conn.execute("""INSERT INTO shows (movie_id, screen_id, start_time, regular_price, premium_price)
                                  VALUES (%s, %s, %s, 200, 350) RETURNING id""", (movie, screen, start)).fetchone()["id"]
        seats = [r["id"] for r in conn.execute("SELECT id FROM seats WHERE screen_id = %s ORDER BY id LIMIT 6", (screen,))]
        staff = {}
        for role in ("SUPER_ADMIN", "MANAGER", "SUPPORT"):
            username = f"t-{role.lower()}-{tag}"
            conn.execute("INSERT INTO admin_users (username, full_name, role, password_hash) VALUES (%s, %s, %s, %s)",
                         (username, f"Test {role}", role, hash_password(PASSWORD)))
            staff[role] = username
        data = {"tag": tag, "show_id": show_id, "seats": seats, "staff": staff, "emails": []}
        yield data
        conn.execute("DELETE FROM seat_holds WHERE show_id = %s", (show_id,))
        conn.execute("DELETE FROM bookings WHERE show_id = %s", (show_id,))
        for email in data["emails"]:
            conn.execute("DELETE FROM customers WHERE lower(email) = lower(%s)", (email,))
            conn.execute("DELETE FROM users WHERE lower(email) = lower(%s)", (email,))
        conn.execute("DELETE FROM shows WHERE id = %s", (show_id,))
        conn.execute("DELETE FROM admin_audit_log WHERE admin_username LIKE %s", (f"%-{tag}",))
        conn.execute("DELETE FROM admin_users WHERE username LIKE %s", (f"%-{tag}",))


def _register(client, env, name="Asha Patil"):
    email = f"user-{secrets.token_hex(4)}-{env['tag']}@example.com"
    env["emails"].append(email)
    response = client.post("/auth/register", json={"full_name": name, "email": email, "password": PASSWORD, "phone": "9812345678"})
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['token']}"}, body["user"]


def _staff(client, env, role):
    response = client.post("/admin/login", json={"username": env["staff"][role], "password": PASSWORD})
    assert response.status_code == 200, response.text
    assert response.json()["role"] == role
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _book(client, env, headers, seat_index=0, email="someone-else@example.com"):
    hold = client.post(f"/shows/{env['show_id']}/holds", json={"seat_ids": [env["seats"][seat_index]]}, headers=headers)
    assert hold.status_code == 201, hold.text
    booking = client.post("/bookings", headers=headers, json={"hold_id": hold.json()["hold_id"], "full_name": "Asha Patil",
                                                              "email": email})
    assert booking.status_code == 202, booking.text
    ref = booking.json()["booking_ref"]
    assert client.get(f"/bookings/{ref}").json()["status"] == "CONFIRMED"     # inline worker confirms at once
    return ref


def test_register_login_profile_logout(client, env):
    headers, user = _register(client, env)
    assert user["phone"] == "+919812345678"
    duplicate = client.post("/auth/register", json={"full_name": "Asha", "email": user["email"].upper(), "password": PASSWORD})
    assert duplicate.status_code == 409
    assert client.post("/auth/login", json={"email": user["email"], "password": "wrong password"}).status_code == 401
    login = client.post("/auth/login", json={"email": user["email"].upper(), "password": PASSWORD})
    assert login.status_code == 200 and login.json()["user"]["id"] == user["id"]
    assert client.get("/auth/me", headers=headers).json()["email"] == user["email"]
    assert client.patch("/auth/me", headers=headers, json={"full_name": "Asha P"}).json()["full_name"] == "Asha P"
    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.post("/auth/register", json={"full_name": "A", "email": "bad", "password": "short"}).status_code == 422


def test_booking_needs_sign_in_and_belongs_to_the_account(client, env):
    response = client.post(f"/shows/{env['show_id']}/holds", json={"seat_ids": [env["seats"][0]]})
    assert response.status_code == 401 and response.json() == {"detail": "Please sign in to continue"}
    headers, user = _register(client, env)
    ref = _book(client, env, headers)
    detail = client.get(f"/bookings/{ref}").json()
    assert detail["email"] == user["email"]                     # the account email wins over the form
    mine = client.get("/me/bookings", headers=headers).json()
    assert [b["booking_ref"] for b in mine] == [ref] and mine[0]["cancellable"] is True
    other_headers, _ = _register(client, env, "Other Person")
    assert client.post(f"/me/bookings/{ref}/cancel", headers=other_headers).status_code == 404
    cancelled = client.post(f"/me/bookings/{ref}/cancel", headers=headers)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert client.post(f"/me/bookings/{ref}/cancel", headers=headers).status_code == 409


def test_roles_and_permissions(client, env):
    support, manager, super_admin = (_staff(client, env, role) for role in ("SUPPORT", "MANAGER", "SUPER_ADMIN"))
    me = client.get("/admin/me", headers=support).json()
    assert me["role_label"] == "Support" and "films.manage" not in me["permissions"]
    assert client.get("/admin/dashboard", headers=support).status_code == 200
    assert client.get("/admin/bookings", headers=support).status_code == 200
    for method, path in (("get", "/admin/movies"), ("get", "/admin/staff"), ("get", "/admin/audit"),
                         ("post", f"/admin/shows/{env['show_id']}/cancel")):
        response = getattr(client, method)(path, headers=support, **({"json": {"reason": "test"}} if method == "post" else {}))
        assert response.status_code == 403, path
    assert client.get("/admin/movies", headers=manager).status_code == 200
    assert client.get("/admin/staff", headers=manager).status_code == 403
    assert client.get("/admin/staff", headers=super_admin).status_code == 200
    assert client.get("/admin/dashboard").status_code == 401


def test_admin_cancels_booking_and_show_with_audit(client, env):
    headers, _ = _register(client, env)
    first, second = _book(client, env, headers, 0), _book(client, env, headers, 1)
    support, manager, super_admin = (_staff(client, env, role) for role in ("SUPPORT", "MANAGER", "SUPER_ADMIN"))
    found = client.get("/admin/bookings", headers=support, params={"q": first}).json()
    assert found["total"] == 1 and found["items"][0]["user_id"] is not None
    cancelled = client.post(f"/admin/bookings/{first}/cancel", headers=support, json={"reason": "Customer called the box office"})
    assert cancelled.status_code == 200 and cancelled.json()["cancelled_by"].startswith("ADMIN:")
    result = client.post(f"/admin/shows/{env['show_id']}/cancel", headers=manager, json={"reason": "Projector failure"})
    assert result.status_code == 200 and result.json()["cancelled_bookings"] == 1
    assert result.json()["show"]["status"] == "CANCELLED"
    assert client.get(f"/bookings/{second}").json()["status"] == "CANCELLED"
    hold = client.post(f"/shows/{env['show_id']}/holds", json={"seat_ids": [env["seats"][2]]}, headers=headers)
    assert hold.status_code == 409
    actions = {row["action"] for row in client.get("/admin/audit", headers=super_admin, params={"limit": 200}).json()["items"]}
    assert {"booking.cancel", "show.cancel"} <= actions
    assert set(client.get("/admin/dashboard", headers=support).json()["kpis"]) >= {"revenue_today", "occupancy_next_7_days_pct"}


def test_blocking_a_customer_signs_them_out(client, env):
    headers, user = _register(client, env)
    manager = _staff(client, env, "MANAGER")
    support = _staff(client, env, "SUPPORT")
    assert client.patch(f"/admin/customers/{user['id']}", headers=support, json={"is_blocked": True}).status_code == 403
    assert client.patch(f"/admin/customers/{user['id']}", headers=manager, json={"is_blocked": True}).json()["is_blocked"]
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.post("/auth/login", json={"email": user["email"], "password": PASSWORD}).status_code == 403
    client.patch(f"/admin/customers/{user['id']}", headers=manager, json={"is_blocked": False})
    assert client.post("/auth/login", json={"email": user["email"], "password": PASSWORD}).status_code == 200


def test_staff_management_rules(client, env):
    super_admin = _staff(client, env, "SUPER_ADMIN")
    me = client.get("/admin/me", headers=super_admin).json()
    assert client.patch(f"/admin/staff/{me['id']}", headers=super_admin, json={"is_active": False}).status_code == 409
    created = client.post("/admin/staff", headers=super_admin, json={"username": f"new-{env['tag']}", "full_name": "New Person",
                                                                     "role": "SUPPORT", "password": PASSWORD})
    assert created.status_code == 201 and created.json()["role_label"] == "Support"
    assert client.post("/admin/staff", headers=super_admin, json={"username": f"new-{env['tag']}", "full_name": "Again",
                                                                  "role": "SUPPORT", "password": PASSWORD}).status_code == 409
    new_login = client.post("/admin/login", json={"username": f"new-{env['tag']}", "password": PASSWORD})
    new_headers = {"Authorization": f"Bearer {new_login.json()['token']}"}
    disabled = client.patch(f"/admin/staff/{created.json()['id']}", headers=super_admin, json={"is_active": False})
    assert disabled.status_code == 200 and disabled.json()["is_active"] is False
    assert client.get("/admin/me", headers=new_headers).status_code == 401
    assert client.post("/admin/login", json={"username": f"new-{env['tag']}", "password": PASSWORD}).status_code == 401
