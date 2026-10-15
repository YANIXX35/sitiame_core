# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""A desk account tied to no company only logs in if it is Sitiame staff.

Isolation treats a System User without a Company User Permission as Sitiame
staff, who sees every PME (staff_isolation.py, and no Company user permission
narrows the other doctypes). A PME account created by hand and left without
its company permission would then see every PME's books. Staff is therefore
marked by a role -- one of STAFF_MARKER_ROLES -- and an account with neither
a company nor such a role is refused at login (hooks.py on_session_creation).
The automated signups (/company-signup, "Inscrire une PME", PME360) create
the company permission before the first login, so they are unaffected."""

import frappe
from frappe import _

from sitiame_core.roles import CHARGE_AFFAIRES_ROLE, CREDIT_ANALYST_ROLE
from sitiame_core.staff_isolation import EXEMPT_USERS

# Given to Sitiame staff who hold no other Sitiame role (accountants...)
STAFF_ROLE = "Personnel Sitiame"
PLATFORM_ADMIN_ROLE = "Administrateur Plateforme Sitiame"  # setup.PLATFORM_ADMIN_ROLE (setup.py imports frappe.custom)
STAFF_MARKER_ROLES = frozenset(("System Manager", STAFF_ROLE, CHARGE_AFFAIRES_ROLE, CREDIT_ANALYST_ROLE, PLATFORM_ADMIN_ROLE))


def has_company(user):
	return bool(frappe.db.exists("User Permission", {"user": user, "allow": "Company"}))


def is_unattached(user):
	"""A desk account that would see every PME without being staff."""
	if user in EXEMPT_USERS or frappe.db.get_value("User", user, "user_type") != "System User":
		return False
	if has_company(user):
		return False
	return not (set(frappe.get_roles(user)) & STAFF_MARKER_ROLES)


def check_login(login_manager):
	"""hooks.py on_session_creation: runs on every login, password or token."""
	user = login_manager.user
	if not is_unattached(user):
		return
	frappe.log_error(title="Connexion refusée : compte sans société", message=user)
	frappe.throw(
		_("Votre compte n'est rattaché à aucune société. Contactez SITIAME Capital pour finaliser son ouverture."),
		frappe.AuthenticationError,
	)


def backfill_staff_role():
	"""Once (after_migrate, 2026-10-15): the staff already in place who hold
	no Sitiame role get STAFF_ROLE, so the login check locks nobody out.
	PME accounts (PME Client role) are never marked staff."""
	if frappe.db.get_default("sitiame_staff_role_backfilled"):
		return []
	marked = []
	for user in frappe.get_all("User", filters={"enabled": 1, "user_type": "System User"}, pluck="name"):
		if user in ("Administrator", "Guest") or "PME Client" in frappe.get_roles(user):
			continue
		if is_unattached(user):
			doc = frappe.get_doc("User", user)
			doc.flags.ignore_permissions = True
			doc.add_roles(STAFF_ROLE)
			marked.append(user)
	frappe.db.set_default("sitiame_staff_role_backfilled", "1")
	frappe.db.commit()
	if marked:
		frappe.log_error(title=f"Rôle {STAFF_ROLE} attribué au personnel existant", message="\n".join(marked))
	return marked
