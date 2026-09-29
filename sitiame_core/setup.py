# Copyright (c) 2026, Sitiame Capital
# License: MIT

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from sitiame_core.roles import CHARGE_AFFAIRES_ROLE, CREDIT_ANALYST_ROLE


def after_migrate():
	_create_subscription_fields()
	_create_pay_on_submit_fields()
	make_hr_icon_a_folder()
	add_syscohada_report_to_sidebar()
	add_journal_to_payment_sidebars()
	_ensure_platform_admin_role()
	ensure_credit_analyst_role()
	ensure_charge_affaires_role()
	_create_portfolio_field()
	_grant_crm_permissions()
	ensure_charge_affaires_workspace()


# Grants access to the "Utilisateurs de la plateforme" page (every PME and
# its subscription). Given to people from the User form, never hard-coded.
PLATFORM_ADMIN_ROLE = "Administrateur Plateforme Sitiame"


def _ensure_platform_admin_role():
	_ensure_role(PLATFORM_ADMIN_ROLE)


def ensure_credit_analyst_role():
	_ensure_role(CREDIT_ANALYST_ROLE)


def ensure_charge_affaires_role():
	_ensure_role(CHARGE_AFFAIRES_ROLE)


def _create_portfolio_field():
	"""Company.sitiame_charge_affaires: who follows this PME. Only a
	validator may change it (portfolio.guard_portfolio_field)."""
	create_custom_fields(
		{
			"Company": [
				{
					"fieldname": "sitiame_charge_affaires",
					"label": "Chargé d'affaires",
					"fieldtype": "Link",
					"options": "User",
					"insert_after": "sitiame_subscription_ends_on",
					"no_copy": 1,
					"in_standard_filter": 1,
					"description": "Membre de l'équipe Sitiame qui suit cette PME : lui seul (et les validateurs) la voit dans l'espace Chargé d'affaires.",
				},
			],
		},
		update=True,
	)


# What a chargé d'affaires works in the CRM, and reads of the PMEs. Which
# records he sees is narrowed by portfolio.py (his own leads and
# opportunities, the companies of his portfolio).
CRM_RIGHTS = ("read", "write", "create", "print", "email", "report", "export")
CHARGE_AFFAIRES_GRANTS = {
	"Lead": CRM_RIGHTS,
	"Opportunity": CRM_RIGHTS,
	"Prospect": CRM_RIGHTS,
	"Contact": CRM_RIGHTS,
	"Company": ("read", "print", "report"),
}


def _grant_crm_permissions():
	"""add_permission copies the standard permissions into Custom DocPerm
	first: a Custom DocPerm alone would replace them for every role."""
	from frappe.permissions import add_permission, update_permission_property

	for doctype, rights in CHARGE_AFFAIRES_GRANTS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		if not frappe.db.exists(
			"Custom DocPerm", {"parent": doctype, "role": CHARGE_AFFAIRES_ROLE, "permlevel": 0, "if_owner": 0}
		):
			add_permission(doctype, CHARGE_AFFAIRES_ROLE, 0)
		for right in rights:
			update_permission_property(doctype, CHARGE_AFFAIRES_ROLE, 0, right, 1, validate=False)
	frappe.db.commit()


CHARGE_AFFAIRES_SIDEBAR = "Chargé d'affaires"
CHARGE_AFFAIRES_PAGE = "erp-charge-affaires"
# (label, link_type, link_to)
CHARGE_AFFAIRES_ITEMS = (
	("Mon portefeuille", "Page", CHARGE_AFFAIRES_PAGE),
	("Prospects", "DocType", "Lead"),
	("Opportunités", "DocType", "Opportunity"),
	("Dossiers de scoring", "DocType", "Credit Scoring Dossier"),
	("Dossiers de financement", "DocType", "Financing Dossier"),
	("Classement financier", "Page", "erp-financial-ranking"),
	("Liasse SYSCOHADA", "Report", "Liasse SYSCOHADA"),
	("Documents KYC", "Page", "erp-kyc"),
	("Abonnements des PME", "Page", "erp-abonnement"),
)


def ensure_charge_affaires_workspace():
	"""Sidebar + home icon of the chargé d'affaires space, built like the
	"Scoring" ones. Rewritten on every migrate so the list stays the one
	above."""
	if frappe.db.exists("Workspace Sidebar", CHARGE_AFFAIRES_SIDEBAR):
		sidebar = frappe.get_doc("Workspace Sidebar", CHARGE_AFFAIRES_SIDEBAR)
		sidebar.items = []
	else:
		sidebar = frappe.new_doc("Workspace Sidebar")
		sidebar.title = CHARGE_AFFAIRES_SIDEBAR
	sidebar.header_icon = "users"
	sidebar.module = "Sitiame Core"
	for label, link_type, link_to in CHARGE_AFFAIRES_ITEMS:
		sidebar.append(
			"items", {"label": label, "type": "Link", "link_type": link_type, "link_to": link_to, "icon": "users"}
		)
	sidebar.flags.ignore_permissions = True
	sidebar.flags.ignore_links = True
	if sidebar.is_new():
		sidebar.insert()
	else:
		sidebar.save()

	if not frappe.db.exists("Desktop Icon", CHARGE_AFFAIRES_SIDEBAR):
		icon = frappe.get_doc(
			{
				"doctype": "Desktop Icon",
				"label": CHARGE_AFFAIRES_SIDEBAR,
				"icon_type": "Link",
				"link_type": "Workspace Sidebar",
				"link_to": CHARGE_AFFAIRES_SIDEBAR,
				"icon": "users",
				"icon_image": "/assets/erpnext/icons/desktop_icons/solid/crm.svg",
				"bg_color": "green",
				"app": "sitiame_core",
				# not a tile for the rest of the team
				"roles": [{"role": CHARGE_AFFAIRES_ROLE}, {"role": "System Manager"}],
			}
		)
		icon.insert(ignore_permissions=True)
	frappe.db.commit()
	frappe.clear_cache()


def _ensure_role(role):
	if not frappe.db.exists("Role", role):
		frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
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
