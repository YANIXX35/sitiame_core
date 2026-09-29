# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""A chargé d'affaires only sees the PMEs of his portfolio
(Company.sitiame_charge_affaires = him), and prepares their dossiers
without deciding them.

User Permissions on Company are NOT used for this: they are what makes an
account a PME account (subscription_api.get_user_company, staff_isolation).
The narrowing is done by permission hooks instead, which touch nobody
but a chargé d'affaires (a validator keeps seeing everything).

Company, Credit Scoring Dossier, Financing Dossier: portfolio only. Lead,
Opportunity: his own (created by him or given to him). The reports and
APIs that check frappe.has_permission("Company", ...) (Liasse SYSCOHADA,
Journal des écritures, Scoring 360) are thereby locked to the portfolio
too."""

import json

import frappe
from frappe import _

from sitiame_core.roles import CHARGE_AFFAIRES_ROLE, VALIDATOR_ROLES

PORTFOLIO_FIELD = "sitiame_charge_affaires"
COMPANY_DOCTYPES = ("Credit Scoring Dossier", "Financing Dossier")
# doctype -> the field naming who the record is given to, besides its owner
OWN_RECORD_FIELDS = {"Lead": "lead_owner", "Opportunity": "opportunity_owner"}
PORTFOLIO_DOCTYPES = ("Company", *COMPANY_DOCTYPES, *OWN_RECORD_FIELDS)

UNDECIDED_DECISION = "En attente"
PROPOSAL_STATUSES = ("A examiner", "En cours d'analyse")


def is_charge_affaires(user=None):
	"""Has the role and is not also a validator (who sees everything)."""
	roles = set(frappe.get_roles(user or frappe.session.user))
	return CHARGE_AFFAIRES_ROLE in roles and not roles.intersection(VALIDATOR_ROLES)


def portfolio(user=None):
	"""Companies followed by `user`, cached for the request."""
	user = user or frappe.session.user
	cache = frappe.local.__dict__.setdefault("sitiame_portfolio", {})
	if user not in cache:
		cache[user] = set(frappe.get_all("Company", filters={PORTFOLIO_FIELD: user}, pluck="name", ignore_permissions=True))
	return cache[user]


def in_portfolio(company, user=None):
	return company in portfolio(user)


def check_company(company, user=None):
	"""For the APIs a chargé d'affaires may call: refuses a PME outside his
	portfolio. Nothing for anyone else."""
	if is_charge_affaires(user) and not in_portfolio(company, user):
		frappe.throw(_("Cette PME ne fait pas partie de votre portefeuille."), frappe.PermissionError)


def get_permission_query_conditions(user=None, doctype=None):
	user = user or frappe.session.user
	if doctype not in PORTFOLIO_DOCTYPES or not is_charge_affaires(user):
		return ""
	if doctype in OWN_RECORD_FIELDS:
		me = frappe.db.escape(user)
		return f"(`tab{doctype}`.`owner` = {me} or `tab{doctype}`.`{OWN_RECORD_FIELDS[doctype]}` = {me})"

	companies = portfolio(user)
	if not companies:
		return "1=0"
	column = "name" if doctype == "Company" else "company"
	values = ", ".join(frappe.db.escape(company) for company in sorted(companies))
	return f"`tab{doctype}`.`{column}` in ({values})"


def has_permission(doc, ptype=None, user=None, debug=False):
	# Frappe treats any falsy return as a refusal: always answer True/False.
	user = user or frappe.session.user
	if doc.doctype not in PORTFOLIO_DOCTYPES or not is_charge_affaires(user):
		return True
	if doc.doctype in OWN_RECORD_FIELDS:
		# a new record is his own
		if doc.is_new():
			return True
		return user in (doc.get("owner"), doc.get(OWN_RECORD_FIELDS[doc.doctype]))
	company = doc.name if doc.doctype == "Company" else doc.get("company")
	if not company:
		# a dossier being created, company not chosen yet
		return doc.doctype != "Company"
	return company in portfolio(user)


def check_decision(doc, method=None):
	"""Four eyes: a chargé d'affaires proposes, a validator decides."""
	if not is_charge_affaires():
		return
	if doc.doctype == "Credit Scoring Dossier":
		if (doc.get("decision") or UNDECIDED_DECISION) != UNDECIDED_DECISION or doc.get("validator"):
			frappe.throw(_("La décision de crédit revient à un validateur : laissez « Décision » sur « En attente » et cochez « Prêt » quand le dossier est complet."))
	elif doc.doctype == "Financing Dossier":
		if doc.get("status") and doc.status not in PROPOSAL_STATUSES:
			frappe.throw(_("L'avis sur le financement revient à un validateur : le statut reste « A examiner » ou « En cours d'analyse »."))


OPEN_OPPORTUNITY_STATUSES = ("Open", "Replied", "Quotation")


@frappe.whitelist()
def get_charge_affaires_dashboard():
	"""The "Chargé d'affaires" page: his PMEs with their subscription and
	latest dossiers, his follow-ups, and the dossiers left to complete. A
	validator opening the page sees the PMEs given to him, if any."""
	frappe.only_for((CHARGE_AFFAIRES_ROLE, *VALIDATOR_ROLES))
	from sitiame_core.subscription_api import get_company_subscription

	user = frappe.session.user
	companies = sorted(portfolio(user))

	scorings = _latest_by_company(
		"Credit Scoring Dossier", companies, ["name", "company", "score", "grade", "decision", "ready", "modified"]
	)
	financings = _latest_by_company(
		"Financing Dossier", companies, ["name", "company", "status", "amount_requested", "modified"]
	)

	pme = []
	for company in companies:
		pme.append(
			{
				"company": company,
				"company_name": frappe.db.get_value("Company", company, "company_name") or company,
				"subscription": get_company_subscription(company),
				"scoring": scorings.get(company),
				"financing": financings.get(company),
			}
		)

	return {
		"pme": pme,
		"relances": {
			"todos": frappe.get_all(
				"ToDo",
				filters={"allocated_to": user, "status": "Open"},
				fields=["name", "description", "date", "reference_type", "reference_name"],
				order_by="date asc",
				limit=20,
			),
			"opportunities": frappe.get_all(
				"Opportunity",
				filters={"opportunity_owner": user, "status": ["in", OPEN_OPPORTUNITY_STATUSES]},
				fields=["name", "title", "customer_name", "status", "opportunity_amount", "transaction_date"],
				order_by="transaction_date asc",
				limit=20,
			),
		},
		"a_completer": {
			"scorings": [s for s in scorings.values() if not s.get("ready")],
			"financings": [f for f in financings.values() if f.get("status") == "A examiner"],
		},
	}


def _latest_by_company(doctype, companies, fields):
	latest = {}
	if not companies:
		return latest
	for row in frappe.get_all(
		doctype, filters={"company": ["in", companies]}, fields=fields, order_by="modified desc"
	):
		latest.setdefault(row.company, row)
	return latest


# Home tiles a chargé d'affaires keeps; every other one is hidden for him.
CHARGE_AFFAIRES_ICONS = ("Chargé d'affaires", "CRM", "Scoring", "Financement")


@frappe.whitelist()
def configure_charge_affaires(user):
	"""One click from the User form: gives the role and hides every other
	home tile (sitiame_hidden_desktop_icons, read by boot.py)."""
	frappe.only_for("System Manager")
	doc = frappe.get_doc("User", user)
	doc.add_roles(CHARGE_AFFAIRES_ROLE)
	top_level = frappe.get_all(
		"Desktop Icon", filters={"parent_icon": ["is", "not set"], "hidden": 0}, pluck="label"
	)
	hidden = sorted({label for label in top_level if label and label not in CHARGE_AFFAIRES_ICONS})
	frappe.db.set_value("User", user, "sitiame_hidden_desktop_icons", json.dumps(hidden))
	frappe.clear_cache(user=user)
	return {"hidden": hidden}


def guard_portfolio_field(doc, method=None):
	"""Only a validator gives a PME to a chargé d'affaires: a PME account
	(Accounts Manager on its own Company) must not pick its own."""
	if doc.is_new() or not doc.has_value_changed(PORTFOLIO_FIELD):
		return
	if not set(frappe.get_roles()).intersection(VALIDATOR_ROLES):
		frappe.throw(_("Seul un administrateur peut attribuer une PME à un chargé d'affaires."), frappe.PermissionError)
