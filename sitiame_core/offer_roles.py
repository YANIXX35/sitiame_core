# Copyright (c) 2026, Sitiame Capital
# License: MIT
#
# Keeps the PME360 offer role (PME360 Essentiel / Pilotage / Transformation)
# in sync with Company.sitiame_offer. Called from two places:
#   - hooks.py Company.on_update  (when an admin changes the offer)
#   - api.py at registration time (new PME gets PME360 Essentiel by default)
#
# NEVER removes ERPNext core roles (Accounts Manager, Sales Manager, …):
# those are still the actual permission carriers. The offer role is an
# identifier that lets Python code read the offer without an extra DB query.

import frappe

from sitiame_core.roles import PME360_OFFER_ROLES, _OFFER_TO_ROLE


def offer_role_for(offer):
	"""Return the role name for the given offer string, defaulting to Essentiel."""
	return _OFFER_TO_ROLE.get(offer or "Essentiel", _OFFER_TO_ROLE["Essentiel"])


def sync_offer_role(user_email, offer):
	"""Set exactly one offer role on a PME user. Swaps atomically: removes the
	old offer roles and adds the new one. Never touches non-offer roles."""
	if not frappe.db.exists("User", user_email):
		return

	target_role = offer_role_for(offer)
	user = frappe.get_doc("User", user_email)

	# Remove any existing offer roles
	user.roles = [r for r in user.roles if r.role not in PME360_OFFER_ROLES]
	user.save(ignore_permissions=True)

	# Add the correct one
	user.add_roles(target_role)


def sync_offer_role_on_company_update(doc, method=None):
	"""Frappe hook: Company.on_update. Swaps the offer role on the PME user
	only when sitiame_offer actually changed (avoids no-op saves)."""
	try:
		if not doc.has_value_changed("sitiame_offer"):
			return

		# Find the PME user tied to this company (User Permission)
		user_email = frappe.db.get_value(
			"User Permission",
			{"allow": "Company", "for_value": doc.name},
			"user",
		)
		if not user_email:
			return

		# Only swap for PME accounts (not staff accidentally linked to a company)
		roles = frappe.get_roles(user_email)
		if "PME Client" not in roles:
			return

		sync_offer_role(user_email, doc.sitiame_offer)

	except Exception:
		frappe.log_error(
			title=f"sitiame_core.offer_roles: sync failed for company {doc.name}"
		)
