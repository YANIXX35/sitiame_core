# Copyright (c) 2026, Sitiame Capital
# License: MIT

import os

import frappe
from frappe.utils import get_backups_path

# How many 4-hourly ERPNext database backups to keep on disk -- 60 backups
# at a 4h cadence is 10 days of history, same retention window PME360's own
# DatabaseBackupService uses for its (separate) database.
BACKUP_KEEP_COUNT = 60

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
		fields=["name", "email", "company"],
	)

	for row in expired:
		# A PME that paid its subscription (sitiame_subscription_ends_on,
		# see subscription_api.py) keeps its access past the trial.
		subscription_ends_on = row.company and frappe.db.get_value(
			"Company", row.company, "sitiame_subscription_ends_on"
		)
		if subscription_ends_on and frappe.utils.getdate(subscription_ends_on) >= frappe.utils.getdate():
			continue

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


def run_scheduled_backup():
	"""Cron job (every 4h, see hooks.py): create a fresh ERPNext database
	backup and prune old ones, same mechanism as the manual "Lancer une
	sauvegarde maintenant" button on the Sauvegardes ERPNext page."""
	try:
		from frappe.utils.backups import new_backup

		new_backup(ignore_files=True)
		_prune_old_backups()
	except Exception:
		frappe.log_error(
			title="sitiame_core.tasks.run_scheduled_backup",
			message=frappe.get_traceback(),
		)


def _prune_old_backups():
	backups_dir = get_backups_path()
	if not os.path.isdir(backups_dir):
		return

	files = [
		os.path.join(backups_dir, fname)
		for fname in os.listdir(backups_dir)
		if fname.endswith((".sql.gz", ".sql"))
	]
	files.sort(key=os.path.getmtime, reverse=True)

	for path in files[BACKUP_KEEP_COUNT:]:
		os.remove(path)
