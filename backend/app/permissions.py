"""Staff roles and what each may do. One table, used by the API and sent to the admin website.

SUPER_ADMIN  runs the system: everything, including staff accounts and the audit log.
MANAGER      runs the cinemas: films, cinemas, shows, customer blocking, plus everything SUPPORT can do.
SUPPORT      helps customers: sees the dashboard, bookings and customers, and can cancel and refund a booking.
"""
ROLES = ("SUPER_ADMIN", "MANAGER", "SUPPORT")

_SUPPORT = {"dashboard.view", "bookings.view", "bookings.cancel", "customers.view"}
_MANAGER = _SUPPORT | {"films.manage", "cinemas.manage", "shows.manage", "customers.block"}
_SUPER_ADMIN = _MANAGER | {"staff.manage", "audit.view"}

PERMISSIONS: dict[str, frozenset[str]] = {
    "SUPPORT": frozenset(_SUPPORT),
    "MANAGER": frozenset(_MANAGER),
    "SUPER_ADMIN": frozenset(_SUPER_ADMIN),
}

ROLE_LABELS = {"SUPER_ADMIN": "Super admin", "MANAGER": "Manager", "SUPPORT": "Support"}


def permissions_for(role: str) -> list[str]:
    return sorted(PERMISSIONS.get(role, frozenset()))


def allowed(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, frozenset())
