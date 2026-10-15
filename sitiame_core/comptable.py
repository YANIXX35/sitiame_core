# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Espace comptable : données du tableau de bord pour la page erp-comptable."""

import frappe
from frappe import _

from sitiame_core.party_isolation import SITIAME_COMPANY
from sitiame_core.subscription_api import get_company_subscription


@frappe.whitelist()
def get_comptable_dashboard():
	"""Retourne la liste de toutes les sociétés PME avec leur statut
	d'abonnement et la date de leur dernière écriture comptable.
	Réservé aux comptables et administrateurs Sitiame (staff sans company propre)."""
	roles = set(frappe.get_roles())
	if not {"Accounts Manager", "System Manager"} & roles:
		frappe.throw(_("Réservé aux comptables et administrateurs."), frappe.PermissionError)
	# Faille 2026-10-12: PME accounts have Accounts Manager too — staff only.
	from sitiame_core.party_isolation import company_of
	if company_of(frappe.session.user):
		frappe.throw(_("Réservé aux comptables Sitiame."), frappe.PermissionError)

	companies = frappe.get_all(
		"Company",
		filters=[["name", "!=", SITIAME_COMPANY]],
		fields=["name", "company_name", "default_currency"],
		order_by="company_name asc",
	)

	result = []
	for c in companies:
		last_entry = frappe.db.get_value(
			"Journal Entry",
			{"company": c.name, "docstatus": 1},
			"posting_date",
			order_by="posting_date desc",
		)
		result.append({
			"company": c.name,
			"company_name": c.company_name or c.name,
			"currency": c.default_currency or "XOF",
			"last_entry": str(last_entry) if last_entry else None,
			"subscription": get_company_subscription(c.name),
		})

	return result
