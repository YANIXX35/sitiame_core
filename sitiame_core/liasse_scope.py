# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Whose books a PME account sees. A PME account runs its own activity, even
when several accounts share a company (asked 2026-10-16): its liasse, ledger
and reports are built from the vouchers it created only, and nobody in the
company sees the company-wide books. Sitiame staff still see the whole company.

Filtered on the voucher's owner rather than the ledger line's: ERPNext reposts
stock ledger lines in background jobs (as Administrator), which would drop
them from their account's books."""

import frappe
from frappe import _

PARAM = "liasse_owner"

# ledgers whose lines carry voucher_type / voucher_no; ERPNext's reports apply
# their permission query conditions (General Ledger, financial statements,
# receivables / payables, Financial Report Templates)
LEDGER_DOCTYPES = ("GL Entry", "Payment Ledger Entry")

# reports that read the ledger without permission conditions: refused to a
# PME account sharing its company, whose figures they would mix
UNSCOPED_REPORTS = frozenset(["Trial Balance"])


def liasse_owner(user=None):
	"""The PME account whose books are computed, None for the whole company."""
	user = user or frappe.session.user
	if user == "Administrator" or "PME Client" not in frappe.get_roles(user):
		return None
	return user


def _voucher_parts(company, table, prefix, owner_sql):
	parts = []
	for voucher_type in frappe.db.sql_list(
		f"select distinct voucher_type from `tab{table}` where company = %s", company
	):
		# voucher types come from the ledger: only real doctypes go into SQL
		if not voucher_type or not frappe.db.exists("DocType", voucher_type):
			continue
		parts.append(
			f"({prefix}voucher_type = {frappe.db.escape(voucher_type)} and {prefix}voucher_no in "
			f"(select name from `tab{voucher_type}` where owner = {owner_sql}))"
		)
	return parts


def owner_condition(company, alias="gle", user=None):
	"""(SQL condition, params) restricting GL entries to the vouchers the PME
	account created; ("", {}) for staff."""
	owner = liasse_owner(user)
	if not owner:
		return "", {}
	prefix = f"{alias}." if alias else ""
	parts = _voucher_parts(company, "GL Entry", prefix, f"%({PARAM})s")
	if not parts:
		return " and 1 = 0", {PARAM: owner}
	return f" and ({' or '.join(parts)})", {PARAM: owner}


def _company(user):
	from sitiame_core.subscription_api import get_user_company

	return get_user_company(user)


def get_permission_query_conditions(user=None, doctype=None):
	"""Ledger lines a PME account may read: its company's, from its vouchers."""
	user = user or frappe.session.user
	if not liasse_owner(user):
		return ""
	company = _company(user)
	if not company:
		return "1 = 0"
	table = f"`tab{doctype}`"
	parts = _voucher_parts(company, doctype, f"{table}.", frappe.db.escape(user))
	if not parts:
		return "1 = 0"
	return f"({table}.company = {frappe.db.escape(company)} and ({' or '.join(parts)}))"


def has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if not liasse_owner(user):
		return True
	if doc.get("company") != _company(user) or not doc.get("voucher_type"):
		return False
	return frappe.db.get_value(doc.voucher_type, doc.voucher_no, "owner") == user


def shares_company(user=None):
	"""A PME account whose company has other PME accounts."""
	user = user or frappe.session.user
	if not liasse_owner(user):
		return False
	company = _company(user)
	others = frappe.get_all(
		"User Permission", {"allow": "Company", "for_value": company, "user": ["!=", user]}, pluck="user"
	)
	return any("PME Client" in frappe.get_roles(other) for other in others)


def guard_unscoped_report(report_name):
	if report_name in UNSCOPED_REPORTS and shares_company():
		frappe.throw(
			_(
				"La {0} regroupe tous les comptes de la société. Utilisez le Grand livre "
				"ou les états SYSCOHADA, calculés sur vos propres opérations."
			).format(_(report_name)),
			frappe.PermissionError,
		)


def patch_unscoped_reports():
	"""before_request / before_job: wrap the reports of UNSCOPED_REPORTS once
	per process so that every path (screen, export, prepared report) checks."""
	from erpnext.accounts.report.trial_balance import trial_balance

	if getattr(trial_balance.execute, "_sitiame_guarded", False):
		return
	original = trial_balance.execute

	def execute(filters=None):
		guard_unscoped_report("Trial Balance")
		return original(filters)

	execute._sitiame_guarded = True
	trial_balance.execute = execute
