# Copyright (c) 2026, Sitiame Capital
# License: MIT

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from sitiame_core.roles import CHARGE_AFFAIRES_ROLE, CREDIT_ANALYST_ROLE


def after_migrate():
	_create_subscription_fields()
	_create_offer_field()
	_create_offer_roles()
	_migrate_offer_roles()
	_create_pay_on_submit_fields()
	_create_party_company_fields()
	_create_withholding_field()
	make_hr_icon_a_folder()
	add_syscohada_report_to_sidebar()
	add_journal_to_payment_sidebars()
	_ensure_platform_admin_role()
	ensure_credit_analyst_role()
	ensure_charge_affaires_role()
	_create_portfolio_field()
	_create_tax_regime_field()
	_grant_crm_permissions()
	ensure_charge_affaires_workspace()
	ensure_tableau_de_bord_icon()
	ensure_plateforme_utilisateurs_icon()
	ensure_admin_dashboard_icon()


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


def _create_tax_regime_field():
	"""Company.sitiame_regime_fiscal: the PME's Ivorian tax regime, which
	decides whether the scanned-invoice import recovers the VAT (RSI/RNI)
	or adds it to the cost (TEE/RME) -- see ocr_plan.py. Left empty on the
	existing companies: the accountant fills it in."""
	create_custom_fields(
		{
			"Company": [
				{
					"fieldname": "sitiame_regime_fiscal",
					"label": "Régime fiscal (Côte d'Ivoire)",
					"fieldtype": "Select",
					"options": "\nTEE\nRME\nRSI\nRNI",
					"insert_after": "tax_id",
					"in_standard_filter": 1,
					"description": (
						"TEE : Taxe d'État de l'entreprenant ; RME : Régime des microentreprises "
						"(ni TVA facturée, ni TVA récupérée) ; RSI : Régime simplifié d'imposition ; "
						"RNI : Régime normal d'imposition (TVA collectée et déductible). "
						"Utilisé par l'import des factures scannées pour traiter la TVA."
					),
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
# (label, link_type, link_to). "Mon portefeuille", "Prospects" and
# "Inscrire une PME" are home tiles of their own instead (asked 2026-09-29).
CHARGE_AFFAIRES_ITEMS = (
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
	_ensure_sidebar(CHARGE_AFFAIRES_SIDEBAR, CHARGE_AFFAIRES_ITEMS)
	_ensure_charge_affaires_icon(
		CHARGE_AFFAIRES_SIDEBAR, "users", "/assets/erpnext/icons/desktop_icons/solid/crm.svg", idx=90
	)
	# Tiles of their own, not entries of the sidebar above. A desk tile is
	# only shown when a sidebar of the same name exists, and opens its first
	# link; a tile pointing to a URL instead is dropped, or opens a new
	# browser tab: each gets a one-entry sidebar.
	for idx, (label, icon, image, link_type, link_to) in enumerate(STANDALONE_TILES, start=91):
		_ensure_sidebar(label, ((label, link_type, link_to),))
		_ensure_charge_affaires_icon(label, icon, image, idx=idx)
	frappe.db.commit()
	# per-user tile lists are cached (frappe get_desktop_icons)
	frappe.cache().delete_value("desktop_icons")
	frappe.clear_cache()


REGISTER_PME_ICON = "Inscrire une PME"
# (label, icon, image, link_type, link_to), in home screen order
STANDALONE_TILES = (
	("Mon portefeuille", "briefcase", "/assets/erpnext/icons/desktop_icons/solid/organization.svg", "Page", CHARGE_AFFAIRES_PAGE),
	("Prospects", "users", "/assets/erpnext/icons/desktop_icons/solid/selling.svg", "DocType", "Lead"),
	(REGISTER_PME_ICON, "add", "/assets/hrms/icons/desktop_icons/solid/recruitment.svg", "Page", "erp-inscrire-pme"),
)


def _ensure_sidebar(title, items):
	if frappe.db.exists("Workspace Sidebar", title):
		sidebar = frappe.get_doc("Workspace Sidebar", title)
		sidebar.items = []
	else:
		sidebar = frappe.new_doc("Workspace Sidebar")
		sidebar.title = title
	sidebar.header_icon = "users"
	sidebar.module = "Sitiame Core"
	for label, link_type, link_to in items:
		sidebar.append(
			"items", {"label": label, "type": "Link", "link_type": link_type, "link_to": link_to, "icon": "users"}
		)
	sidebar.flags.ignore_permissions = True
	sidebar.flags.ignore_links = True
	if sidebar.is_new():
		sidebar.insert()
	else:
		sidebar.save()


def _ensure_charge_affaires_icon(label, icon, image, idx):
	values = {
		"label": label,
		# before Scoring / Financement
		"idx": idx,
		"icon_type": "Link",
		"link_type": "Workspace Sidebar",
		"link_to": label,
		"link": None,
		"icon": icon,
		"icon_image": image,
		# "green" is refused here: the tiles are turned green by
		# public/css/green_desktop_icons.css
		"bg_color": "blue",
		"app": "sitiame_core",
	}
	if frappe.db.exists("Desktop Icon", label):
		frappe.db.set_value("Desktop Icon", label, values)
		return
	frappe.get_doc(
		{
			"doctype": "Desktop Icon",
			**values,
			# not a tile for the rest of the team
			"roles": [{"role": CHARGE_AFFAIRES_ROLE}, {"role": "System Manager"}],
		}
	).insert(ignore_permissions=True)


TDB_SIDEBAR = "Tableau de Bord"
TDB_PAGE    = "erp-tableau-de-bord"


def ensure_tableau_de_bord_icon():
	"""Crée la tuile 'Tableau de Bord' sur le desk ERPNext pour les clients PME.

	Même pattern que les tuiles standalone du chargé d'affaires :
	  1. Un Workspace Sidebar avec un seul item → Page erp-tableau-de-bord
	  2. Un Desktop Icon qui pointe vers ce sidebar (rôle : PME Client)
	Ré-appliqué à chaque migrate pour rester idempotent.
	"""
	_ensure_sidebar(TDB_SIDEBAR, ((TDB_SIDEBAR, "Page", TDB_PAGE),))

	values = {
		"idx": 1,
		"icon_type": "Link",
		"link_type": "Workspace Sidebar",
		"link_to": TDB_SIDEBAR,
		"link": None,
		"icon": "bar-chart",
		"icon_image": None,
		"bg_color": "blue",
		"app": "sitiame_core",
	}
	if frappe.db.exists("Desktop Icon", TDB_SIDEBAR):
		frappe.db.set_value("Desktop Icon", TDB_SIDEBAR, values)
	else:
		frappe.get_doc(
			{
				"doctype": "Desktop Icon",
				"label": TDB_SIDEBAR,
				**values,
				"roles": [
					{"role": "PME Client"},
					{"role": "Accounts Manager"},
					{"role": "System Manager"},
				],
			}
		).insert(ignore_permissions=True)

	frappe.db.commit()
	frappe.cache().delete_value("desktop_icons")
	frappe.clear_cache()


PLATEFORME_USERS_SIDEBAR = "Utilisateurs de la plateforme"
PLATEFORME_USERS_PAGE    = "erp-plateforme-utilisateurs"


def ensure_plateforme_utilisateurs_icon():
	"""Tuile 'Utilisateurs de la plateforme' visible pour tous les admins
	(System Manager + Administrateur Plateforme Sitiame).
	Ré-appliqué à chaque migrate (idempotent)."""
	_ensure_sidebar(
		PLATEFORME_USERS_SIDEBAR,
		((PLATEFORME_USERS_SIDEBAR, "Page", PLATEFORME_USERS_PAGE),),
	)

	values = {
		"idx": 95,
		"icon_type": "Link",
		"link_type": "Workspace Sidebar",
		"link_to": PLATEFORME_USERS_SIDEBAR,
		"link": None,
		"icon": "users",
		"icon_image": None,
		"bg_color": "blue",
		"app": "sitiame_core",
	}
	existing = frappe.db.get_value("Desktop Icon", {"label": PLATEFORME_USERS_SIDEBAR}, "name")
	if existing:
		frappe.db.set_value("Desktop Icon", existing, values)
	else:
		frappe.get_doc(
			{
				"doctype": "Desktop Icon",
				"label": PLATEFORME_USERS_SIDEBAR,
				**values,
			}
		).insert(ignore_permissions=True)

	# S'assurer que l'icône est visible (non masquée) pour les admins
	# en supprimant toute icône per-user masquée pour ce label
	frappe.db.sql(
		"UPDATE `tabDesktop Icon` SET hidden=0 "
		"WHERE label=%s AND owner IS NOT NULL",
		PLATEFORME_USERS_SIDEBAR,
	)

	frappe.db.commit()
	frappe.cache().delete_value("desktop_icons")
	frappe.clear_cache()


ADMIN_DASHBOARD_SIDEBAR = "Tableau de Bord Admin"
ADMIN_DASHBOARD_PAGE    = "erp-admin-dashboard"


def ensure_admin_dashboard_icon():
	"""Tuile 'Tableau de Bord Admin' pour System Manager et Administrateur
	Plateforme Sitiame. Cachée aux PME Client via boot.py. Idempotent."""
	_ensure_sidebar(
		ADMIN_DASHBOARD_SIDEBAR,
		((ADMIN_DASHBOARD_SIDEBAR, "Page", ADMIN_DASHBOARD_PAGE),),
	)

	values = {
		"idx": 2,
		"icon_type": "Link",
		"link_type": "Workspace Sidebar",
		"link_to": ADMIN_DASHBOARD_SIDEBAR,
		"link": None,
		"icon": "dashboard",
		"icon_image": None,
		"bg_color": "blue",
		"app": "sitiame_core",
	}
	existing = frappe.db.get_value("Desktop Icon", {"label": ADMIN_DASHBOARD_SIDEBAR}, "name")
	if existing:
		frappe.db.set_value("Desktop Icon", existing, values)
	else:
		frappe.get_doc(
			{
				"doctype": "Desktop Icon",
				"label": ADMIN_DASHBOARD_SIDEBAR,
				**values,
			}
		).insert(ignore_permissions=True)

	frappe.db.sql(
		"UPDATE `tabDesktop Icon` SET hidden=0 WHERE label=%s AND owner IS NOT NULL",
		ADMIN_DASHBOARD_SIDEBAR,
	)

	frappe.db.commit()
	frappe.cache().delete_value("desktop_icons")
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


def _create_party_company_fields():
	"""Re-checked on every migrate (sitiame_core.party_isolation)."""
	from sitiame_core.party_isolation import create_company_fields

	create_company_fields()


def _create_withholding_field():
	"""Supplier.sitiame_withholding_type : type de retenue à la source applicable
	au fournisseur selon son régime fiscal ivoirien (BNC/BIC 7,5% ou RME 2%)."""
	create_custom_fields(
		{
			"Supplier": [
				{
					"fieldname": "sitiame_withholding_type",
					"label": "Retenue à la source (CI)",
					"fieldtype": "Select",
					"options": "\nBNC/BIC 7,5%\nRME 2%",
					"insert_after": "tax_id",
					"in_standard_filter": 1,
					"description": (
						"BNC/BIC 7,5% : retenue sur honoraires et prestations de professions libérales "
						"ou entreprises sous régime BNC/BIC. "
						"RME 2% : retenue sur achats auprès d'un fournisseur microentreprise. "
						"Laissé vide si aucune retenue ne s'applique."
					),
				},
			],
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


# Levels of service (Essentiel → Pilotage → Transformation). Controls which
# modules are visible in the PME desk and which tariff applies. Stored on
# Company so the accountant sets it once, at signup or upgrade.
PME360_OFFERS = ("Essentiel", "Pilotage", "Transformation")
PME360_OFFER_FIELD = "sitiame_offer"


def _create_offer_roles():
	"""Create the three offer roles. Idempotent: _ensure_role skips if exists."""
	from sitiame_core.roles import PME360_OFFER_ROLES
	for role in PME360_OFFER_ROLES:
		_ensure_role(role)


def _migrate_offer_roles():
	"""Assign the right offer role to every existing PME account that doesn't
	have one yet. Additive only: never removes ERPNext or other roles."""
	from sitiame_core.roles import PME360_OFFER_ROLES, _OFFER_TO_ROLE

	# All users with the PME Client role that are missing any offer role
	pme_users = frappe.db.sql(
		"""
		SELECT u.name AS user, c.name AS company, c.sitiame_offer AS offer
		FROM `tabUser` u
		JOIN `tabUser Permission` up ON up.user = u.name AND up.allow = 'Company'
		JOIN `tabCompany` c ON c.name = up.for_value
		WHERE u.enabled = 1
		  AND EXISTS (
			SELECT 1 FROM `tabHas Role` hr
			WHERE hr.parent = u.name AND hr.role = 'PME Client'
		  )
		  AND NOT EXISTS (
			SELECT 1 FROM `tabHas Role` hr2
			WHERE hr2.parent = u.name AND hr2.role IN ({roles})
		  )
		""".format(roles=", ".join(f"'{r}'" for r in PME360_OFFER_ROLES)),
		as_dict=True,
	)

	for row in pme_users:
		try:
			offer = row.offer or "Essentiel"
			role  = _OFFER_TO_ROLE.get(offer, _OFFER_TO_ROLE["Essentiel"])
			user  = frappe.get_doc("User", row.user)
			user.add_roles(role)
		except Exception:
			frappe.log_error(title=f"sitiame_core.setup._migrate_offer_roles: {row.user}")

	if pme_users:
		frappe.db.commit()


def _create_offer_field():
	create_custom_fields(
		{
			"Company": [
				{
					"fieldname": PME360_OFFER_FIELD,
					"label": "Offre PME360",
					"fieldtype": "Select",
					"options": "\n" + "\n".join(PME360_OFFERS),
					"insert_after": "sitiame_subscription_ends_on",
					"default": "Essentiel",
					"in_standard_filter": 1,
					"description": (
						"Essentiel : le dirigeant saisit, SITIAME supervise. "
						"Pilotage : SITIAME tient la gestion admin et financière. "
						"Transformation : SITIAME digitalise toute la gestion et prépare le financement."
					),
				},
			],
		},
		update=True,
	)
