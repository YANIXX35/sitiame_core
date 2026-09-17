# Copyright (c) 2026, Sitiame Capital
# License: MIT

import frappe

# Facture (Sales Invoice), Comptabilite (Journal Entry, GL) and Tresorerie
# (Payment Entry, Bank) access in ERPNext is granted through these roles.
# Removing them is a real permission change (frappe.has_permission() then
# correctly denies both API and desk access) -- unlike User.block_modules,
# which only hides sidebar navigation and does NOT restrict actual data
# access (confirmed empirically: Sales Invoice/Journal Entry stayed
# readable via the API even after being added to block_modules).
TRIAL_ROLES = ["Accounts Manager", "Sales Manager", "Purchase Manager"]


def block_expired_trials():
	"""Daily scheduled job: revoke the roles above for any Company Signup
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
			_revoke_trial_roles(row.email)
			frappe.db.set_value("Company Signup", row.name, "trial_blocked", 1)
		except Exception:
			frappe.log_error(
				title="sitiame_core.tasks.block_expired_trials",
				message=frappe.get_traceback(),
			)

	if expired:
		frappe.db.commit()


@frappe.whitelist()
def force_block_for_testing(company_signup_name):
	"""System Manager only: manually trigger the block for one record, to
	test the mechanism without waiting for a real 30-day trial to elapse."""
	frappe.only_for("System Manager")
	doc = frappe.get_doc("Company Signup", company_signup_name)
	_revoke_trial_roles(doc.email)
	doc.db_set("trial_blocked", 1)
	return {"revoked_roles": TRIAL_ROLES, "user": doc.email}


def _revoke_trial_roles(user_email):
	if not frappe.db.exists("User", user_email):
		return

	user = frappe.get_doc("User", user_email)
	user.roles = [row for row in user.roles if row.role not in TRIAL_ROLES]
	user.save(ignore_permissions=True)
