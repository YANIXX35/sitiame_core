# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Sitiame staff accounts do not see each other's business documents.

A PME account is already confined to its own company by its Company User
Permission. Staff accounts have none (they must keep seeing every company
for scoring, financing and audit), so until now every staff member saw
the invoices, payments, customers... that any other staff member had
created in the shared SITIAME company.

Rule, for a staff user on the doctypes below: a document created by
another staff member is hidden. Everything else stays visible: their own
documents, and those created by PME accounts, the PME360 integration
user or Administrator. PME accounts and the exempt users are untouched.

"Staff" = a System User without a Company User Permission, other than
the exempt users."""

import frappe

ISOLATED_DOCTYPES = (
	"Sales Invoice",
	"Purchase Invoice",
	"POS Invoice",
	"Payment Entry",
	"Journal Entry",
	"Quotation",
	"Sales Order",
	"Delivery Note",
	"Supplier Quotation",
	"Request for Quotation",
	"Purchase Order",
	"Purchase Receipt",
	"Material Request",
	"Stock Entry",
	"Stock Reconciliation",
	"Customer",
	"Supplier",
	"Item",
)

# See everything, and their documents are visible to all staff.
EXEMPT_USERS = ("Administrator", "api-pme360@sitiame-capital.com")


def _staff_users():
	"""Every staff account, cached for the request."""
	if getattr(frappe.local, "sitiame_staff_users", None) is None:
		frappe.local.sitiame_staff_users = set(
			frappe.db.sql_list(
				"""
				select u.name from `tabUser` u
				where u.user_type = 'System User'
					and u.name not in %(exempt)s
					and not exists (
						select 1 from `tabUser Permission` up
						where up.user = u.name and up.allow = 'Company'
					)
				""",
				{"exempt": EXEMPT_USERS},
			)
		)
	return frappe.local.sitiame_staff_users


def _hidden_owners(user):
	"""Owners whose documents `user` must not see (empty if not staff)."""
	staff = _staff_users()
	if user not in staff:
		return set()
	return staff - {user}


def get_permission_query_conditions(user=None, doctype=None):
	user = user or frappe.session.user
	if doctype not in ISOLATED_DOCTYPES:
		return ""
	hidden = _hidden_owners(user)
	if not hidden:
		return ""
	owners = ", ".join(frappe.db.escape(owner) for owner in sorted(hidden))
	return f"`tab{doctype}`.`owner` not in ({owners})"


def has_permission(doc, ptype=None, user=None, debug=False):
	# Frappe treats any falsy return as a refusal: always answer True/False.
	user = user or frappe.session.user
	if doc.doctype not in ISOLATED_DOCTYPES or not doc.get("owner"):
		return True
	return doc.owner not in _hidden_owners(user)
