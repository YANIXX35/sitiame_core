# Copyright (c) 2026, Sitiame Capital
# License: MIT

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_migrate():
	_create_subscription_fields()
	_create_pay_on_submit_fields()
	make_hr_icon_a_folder()
	add_syscohada_report_to_sidebar()
	add_journal_to_payment_sidebars()
	_ensure_platform_admin_role()


# Grants access to the "Utilisateurs de la plateforme" page (every PME and
# its subscription). Given to people from the User form, never hard-coded.
PLATFORM_ADMIN_ROLE = "Administrateur Plateforme Sitiame"


def _ensure_platform_admin_role():
	if not frappe.db.exists("Role", PLATFORM_ADMIN_ROLE):
		frappe.get_doc(
			{"doctype": "Role", "role_name": PLATFORM_ADMIN_ROLE, "desk_access": 1}
		).insert(ignore_permissions=True)
		frappe.db.commit()


FINANCIAL_REPORTS_SIDEBAR = "Financial Reports"
SYSCOHADA_REPORT = "Liasse SYSCOHADA"


def add_syscohada_report_to_sidebar():
	"""Put the SYSCOHADA statements first under "Financial Reports", ahead
	of ERPNext's IFRS Balance Sheet. That sidebar is standard (erpnext) and
	may be re-synced by an erpnext update, hence re-checked on every
	migrate; the row is written directly because a standard sidebar can't
	be saved outside developer mode."""
	if not frappe.db.exists("Workspace Sidebar", FINANCIAL_REPORTS_SIDEBAR):
		return
	if frappe.db.exists(
		"Workspace Sidebar Item", {"parent": FINANCIAL_REPORTS_SIDEBAR, "link_to": SYSCOHADA_REPORT}
	):
		return

	frappe.db.sql(
		"update `tabWorkspace Sidebar Item` set idx = idx + 1 where parent = %s and idx >= 2",
		FINANCIAL_REPORTS_SIDEBAR,
	)
	item = frappe.get_doc(
		{
			"doctype": "Workspace Sidebar Item",
			"parent": FINANCIAL_REPORTS_SIDEBAR,
			"parenttype": "Workspace Sidebar",
			"parentfield": "items",
			"idx": 2,
			"label": "Liasse SYSCOHADA (Bilan, Résultat)",
			"type": "Link",
			"link_type": "Report",
			"link_to": SYSCOHADA_REPORT,
			"child": 1,
		}
	)
	item.db_insert()
	frappe.db.commit()
	frappe.clear_cache()


JOURNAL_REPORT = "Journal des ecritures"
JOURNAL_SIDEBARS = ("Payments", "Invoicing")


def add_journal_to_payment_sidebars():
	""""Journal des ecritures" right after Journal Entry in the Payments and
	Invoicing sidebars: users looked there for the entries of their
	validated invoices, which ERPNext books on the invoice itself. Standard
	sidebars again (re-checked on every migrate, row written directly)."""
	for sidebar in JOURNAL_SIDEBARS:
		if not frappe.db.exists("Workspace Sidebar", sidebar):
			continue
		if frappe.db.exists("Workspace Sidebar Item", {"parent": sidebar, "link_to": JOURNAL_REPORT}):
			continue
		anchor = frappe.db.get_value("Workspace Sidebar Item", {"parent": sidebar, "link_to": "Journal Entry"}, "idx")
		if not anchor:
			continue

		frappe.db.sql(
			"update `tabWorkspace Sidebar Item` set idx = idx + 1 where parent = %s and idx > %s",
			(sidebar, anchor),
		)
		frappe.get_doc(
			{
				"doctype": "Workspace Sidebar Item",
				"parent": sidebar,
				"parenttype": "Workspace Sidebar",
				"parentfield": "items",
				"idx": anchor + 1,
				"label": "Journal des écritures",
				"type": "Link",
				"link_type": "Report",
				"link_to": JOURNAL_REPORT,
				"child": 1,
			}
		).db_insert()
	frappe.db.commit()
	frappe.clear_cache()


HR_ICON = "Frappe HR"
HR_ICON_LABEL_FR = "RH et Paie"


def make_hr_icon_a_folder():
	"""Re-applied on every migrate so an hrms update can't undo it.

	- hrms ships its "Frappe HR" tile as an App icon linking to
	  /desk/people, a workspace hrms itself no longer ships ("Page people
	  introuvable"). As a Folder, like Accounting, it opens its 9 children.
	- Frappe attaches children to their folder by *label* (desktop_icon.py:
	  permitted_parent_labels, sidebar_header.js folder_map), while the
	  children store parent_icon = "Frappe HR". Relabelling the tile
	  itself to "RH et Paie" (done 2026-09-23) orphaned all 9 of them, so
	  the label stays "Frappe HR" and the French name comes from a
	  Translation record instead (the desk renders __(icon.label))."""
	if not frappe.db.exists("Desktop Icon", HR_ICON):
		return

	frappe.db.set_value(
		"Desktop Icon",
		HR_ICON,
		{
			"label": HR_ICON,
			"icon_type": "Folder",
			"link_type": "Workspace Sidebar",
			"link": None,
			"link_to": None,
			# no logo, so it renders as a folder of its children like Accounting
			"logo_url": None,
		},
	)

	translation = frappe.db.get_value("Translation", {"language": "fr", "source_text": HR_ICON})
	if translation:
		frappe.db.set_value("Translation", translation, "translated_text", HR_ICON_LABEL_FR)
	else:
		frappe.get_doc(
			{"doctype": "Translation", "language": "fr", "source_text": HR_ICON, "translated_text": HR_ICON_LABEL_FR}
		).insert(ignore_permissions=True)

	# PME accounts hide the tile by label (boot.py): keep them hiding it
	# under its restored label.
	for user in frappe.get_all(
		"User",
		filters={"sitiame_hidden_desktop_icons": ["like", f'%"{HR_ICON_LABEL_FR}"%']},
		fields=["name", "sitiame_hidden_desktop_icons"],
	):
		hidden = json.loads(user.sitiame_hidden_desktop_icons)
		hidden = [HR_ICON if label == HR_ICON_LABEL_FR else label for label in hidden]
		frappe.db.set_value("User", user.name, "sitiame_hidden_desktop_icons", json.dumps(hidden))

	frappe.db.commit()
	frappe.translate.clear_cache()
	frappe.clear_cache()


def _create_pay_on_submit_fields():
	"""The two fields read by pay_on_submit.create_payment: an invoice
	already paid gets its Payment Entry when it is validated. Hidden where
	ERPNext already handles the payment itself (Est paye, PDV) and on
	credit/debit notes."""
	create_custom_fields(
		{
			doctype: [
				{
					"fieldname": "sitiame_pay_on_submit",
					"label": "Payée : créer le paiement à la validation",
					"fieldtype": "Check",
					"insert_after": "due_date",
					"no_copy": 1,
					"depends_on": "eval:!doc.is_paid && !doc.is_pos && !doc.is_return",
					"description": "L'écriture de paiement est créée et validée en même temps que la facture.",
				},
				{
					"fieldname": "sitiame_payment_mode",
					"label": "Moyen de paiement",
					"fieldtype": "Link",
					"options": "Mode of Payment",
					"insert_after": "sitiame_pay_on_submit",
					"no_copy": 1,
					"depends_on": "eval:doc.sitiame_pay_on_submit",
					"mandatory_depends_on": "eval:doc.sitiame_pay_on_submit",
				},
			]
			for doctype in ("Purchase Invoice", "Sales Invoice")
		},
		update=True,
	)


def _create_subscription_fields():
	# Idempotent: create_custom_fields updates the field in place if it
	# already exists, so this is safe on every `bench migrate`.
	create_custom_fields(
		{
			"Company": [
				{
					"fieldname": "sitiame_subscription_ends_on",
					"label": "Abonnement SITIAME actif jusqu'au",
					"fieldtype": "Date",
					"insert_after": "abbr",
					"read_only": 1,
					"no_copy": 1,
					"in_standard_filter": 1,
				},
			],
		},
		update=True,
	)
