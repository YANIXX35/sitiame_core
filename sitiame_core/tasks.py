# Copyright (c) 2026, Sitiame Capital
# License: MIT

import frappe

# Facture (Sales Invoice), Comptabilite (Journal Entry, GL) and Tresorerie
# (Payment Entry, Bank) all live under the single ERPNext "Accounts" module.
BLOCKED_MODULE = "Accounts"


def block_expired_trials():
	"""Daily scheduled job: block the Accounts module for any Company Signup
	whose 1-month free trial has ended and hasn't been blocked yet."""
	expired = frappe.get_all(
		"Company Signup",
		filters={
			"trial_ends_on": ["<", frappe.utils.today()],
			"trial_blocked": 0,
		},
		fields=["name", "email"],
	)

	for row in expired:
		try:
			_block_user_module(row.email, BLOCKED_MODULE)
			frappe.db.set_value("Company Signup", row.name, "trial_blocked", 1)
		except Exception:
			frappe.log_error(
				title="sitiame_core.tasks.block_expired_trials",
				message=frappe.get_traceback(),
			)

	if expired:
		frappe.db.commit()


@frappe.whitelist()
def get_my_blocked_workspaces():
	"""Names of the Workspace records that belong to a module blocked for
	the current user -- block_modules restricts sidebar navigation and
	deeper permission checks, but does NOT hide the home-page icon grid
	on its own, so the desk-side JS uses this to hide those icons too."""
	user = frappe.get_cached_doc("User", frappe.session.user)
	blocked_modules = [d.module for d in user.get("block_modules", [])]
	if not blocked_modules:
		return []
	return frappe.get_all("Workspace", filters={"module": ["in", blocked_modules]}, pluck="name")


@frappe.whitelist()
def force_block_for_testing(company_signup_name):
	"""System Manager only: manually trigger the block for one record, to
	test the mechanism without waiting for a real 30-day trial to elapse."""
	frappe.only_for("System Manager")
	doc = frappe.get_doc("Company Signup", company_signup_name)
	_block_user_module(doc.email, BLOCKED_MODULE)
	doc.db_set("trial_blocked", 1)
	return {"blocked_module": BLOCKED_MODULE, "user": doc.email}


def _block_user_module(user_email, module):
	if not frappe.db.exists("User", user_email):
		return

	user = frappe.get_doc("User", user_email)
	already_blocked = any(row.module == module for row in user.get("block_modules", []))
	if already_blocked:
		return

	user.append("block_modules", {"module": module})
	user.save(ignore_permissions=True)
