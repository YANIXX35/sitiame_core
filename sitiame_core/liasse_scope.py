# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Whose books the liasse covers. A PME account runs its own activity, even
when several accounts share a company (asked 2026-10-16): its liasse is built
from the vouchers it created only, and nobody in the company sees the
company-wide one. Sitiame staff still see the whole company.

Filtered on the voucher's owner rather than the GL line's: ERPNext reposts
stock GL lines in background jobs (as Administrator), which would drop them
from their account's liasse."""

import frappe

PARAM = "liasse_owner"


def liasse_owner(user=None):
	"""The PME account whose liasse is computed, None for the whole company."""
	user = user or frappe.session.user
	if user == "Administrator" or "PME Client" not in frappe.get_roles(user):
		return None
	return user


def owner_condition(company, alias="gle", user=None):
	"""(SQL condition, params) restricting GL entries to the vouchers the PME
	account created; ("", {}) for staff."""
	owner = liasse_owner(user)
	if not owner:
		return "", {}
	prefix = f"{alias}." if alias else ""
	parts = []
	for voucher_type in frappe.db.sql_list(
		"select distinct voucher_type from `tabGL Entry` where company = %s", company
	):
		# voucher types come from the ledger: only real doctypes go into SQL
		if not voucher_type or not frappe.db.exists("DocType", voucher_type):
			continue
		parts.append(
			f"({prefix}voucher_type = {frappe.db.escape(voucher_type)} and {prefix}voucher_no in "
			f"(select name from `tab{voucher_type}` where owner = %({PARAM})s))"
		)
	if not parts:
		return " and 1 = 0", {PARAM: owner}
	return f" and ({' or '.join(parts)})", {PARAM: owner}
