# Copyright (c) 2026, Sitiame Capital
# License: MIT
#
# API pour la page "Tableau de Bord PME" — agrège trésorerie, comptabilité,
# achats, ventes et scoring pour la société active de l'utilisateur connecté.

import frappe
from frappe import _
from frappe.utils import flt, nowdate, add_months, get_first_day, get_last_day


def _company():
	"""Retourne la société par défaut de l'utilisateur connecté.
	Pour une PME : lit la Company User Permission (source de vérité).
	Pour le staff : lit le default utilisateur/global comme avant."""
	# Faille 2026-10-12: get_user_default("company") is user-editable and does
	# not filter GL queries; for PME accounts use the authoritative permission.
	from sitiame_core.party_isolation import company_of
	pme_company = company_of(frappe.session.user)
	if pme_company:
		return pme_company
	return frappe.defaults.get_user_default("company") or frappe.defaults.get_global_default("company")


@frappe.whitelist()
def get_dashboard_data():
	"""Retourne toutes les données du tableau de bord pour la société active."""
	frappe.only_for(["PME Client", "Accounts Manager", "System Manager"])
	company = _company()
	if not company:
		# Pas de société configurée : retourner un état vide lisible par le JS
		return {"company": None, "no_company": True}

	today = nowdate()
	first_day = get_first_day(today)
	last_day  = get_last_day(today)

	return {
		"company": company,
		"tresorerie": _tresorerie(company, first_day, last_day),
		"comptabilite": _comptabilite(company, first_day, last_day),
		"achats": _achats(company, first_day, last_day),
		"ventes": _ventes(company, first_day, last_day),
		"scoring": _scoring(company),
		"stock": _stock(company),
		"sparklines": _sparklines(company),
	}


# ── TRÉSORERIE ────────────────────────────────────────────────────────────────

def _tresorerie(company, first_day, last_day):
	# Solde des comptes de trésorerie (classe 5)
	solde = frappe.db.sql("""
		SELECT COALESCE(SUM(debit - credit), 0)
		FROM `tabGL Entry`
		WHERE company = %s
		  AND account LIKE '5%%'
		  AND is_cancelled = 0
	""", company)[0][0] or 0

	encaissements = frappe.db.sql("""
		SELECT COALESCE(SUM(debit), 0)
		FROM `tabGL Entry`
		WHERE company = %s
		  AND account LIKE '5%%'
		  AND is_cancelled = 0
		  AND posting_date BETWEEN %s AND %s
		  AND debit > 0
	""", (company, first_day, last_day))[0][0] or 0

	decaissements = frappe.db.sql("""
		SELECT COALESCE(SUM(credit), 0)
		FROM `tabGL Entry`
		WHERE company = %s
		  AND account LIKE '5%%'
		  AND is_cancelled = 0
		  AND posting_date BETWEEN %s AND %s
		  AND credit > 0
	""", (company, first_day, last_day))[0][0] or 0

	return {
		"solde": flt(solde, 0),
		"encaissements_mois": flt(encaissements, 0),
		"decaissements_mois": flt(decaissements, 0),
	}


# ── COMPTABILITÉ ──────────────────────────────────────────────────────────────

def _comptabilite(company, first_day, last_day):
	total_ecritures = frappe.db.count("GL Entry", {"company": company, "is_cancelled": 0})

	volume_mois = frappe.db.sql("""
		SELECT COALESCE(SUM(debit), 0)
		FROM `tabGL Entry`
		WHERE company = %s
		  AND is_cancelled = 0
		  AND posting_date BETWEEN %s AND %s
	""", (company, first_day, last_day))[0][0] or 0

	derniere_ecriture = frappe.db.get_value(
		"GL Entry",
		{"company": company, "is_cancelled": 0},
		["posting_date", "voucher_no", "remarks"],
		order_by="posting_date desc",
	)

	return {
		"total_ecritures": total_ecritures,
		"volume_mois": flt(volume_mois, 0),
		"derniere_ecriture_date": derniere_ecriture[0] if derniere_ecriture else None,
		"derniere_ecriture_ref": derniere_ecriture[1] if derniere_ecriture else None,
	}


# ── ACHATS ────────────────────────────────────────────────────────────────────

def _achats(company, first_day, last_day):
	total_mois = frappe.db.sql("""
		SELECT COALESCE(SUM(grand_total), 0), COUNT(*)
		FROM `tabPurchase Invoice`
		WHERE company = %s
		  AND docstatus = 1
		  AND posting_date BETWEEN %s AND %s
	""", (company, first_day, last_day))[0]

	en_attente = frappe.db.count("Purchase Invoice", {
		"company": company, "docstatus": 1, "status": ["in", ["Unpaid", "Overdue"]]
	})

	return {
		"montant_mois": flt(total_mois[0], 0),
		"nb_factures_mois": int(total_mois[1] or 0),
		"en_attente_paiement": en_attente,
	}


# ── VENTES ────────────────────────────────────────────────────────────────────

def _ventes(company, first_day, last_day):
	ca_mois = frappe.db.sql("""
		SELECT COALESCE(SUM(grand_total), 0), COUNT(*)
		FROM `tabSales Invoice`
		WHERE company = %s
		  AND docstatus = 1
		  AND posting_date BETWEEN %s AND %s
	""", (company, first_day, last_day))[0]

	ca_total = frappe.db.sql("""
		SELECT COALESCE(SUM(grand_total), 0)
		FROM `tabSales Invoice`
		WHERE company = %s AND docstatus = 1
	""", company)[0][0] or 0

	impayes = frappe.db.count("Sales Invoice", {
		"company": company, "docstatus": 1, "status": ["in", ["Unpaid", "Overdue"]]
	})

	return {
		"ca_mois": flt(ca_mois[0], 0),
		"nb_factures_mois": int(ca_mois[1] or 0),
		"ca_total": flt(ca_total, 0),
		"impayes": impayes,
	}


# ── STOCK ─────────────────────────────────────────────────────────────────────

def _stock(company):
	valeur = frappe.db.sql("""
		SELECT COALESCE(SUM(stock_value), 0)
		FROM `tabBin`
		WHERE warehouse IN (
			SELECT name FROM `tabWarehouse` WHERE company = %s AND disabled = 0
		)
	""", company)[0][0] or 0

	nb_articles = frappe.db.sql("""
		SELECT COUNT(DISTINCT item_code)
		FROM `tabBin`
		WHERE warehouse IN (
			SELECT name FROM `tabWarehouse` WHERE company = %s AND disabled = 0
		)
		  AND actual_qty > 0
	""", company)[0][0] or 0

	return {
		"valeur_stock": flt(valeur, 0),
		"nb_articles": int(nb_articles),
	}


# ── SCORING ───────────────────────────────────────────────────────────────────

def _scoring(company):
	dossier = frappe.db.get_value(
		"Financing Dossier",
		{"company": company},
		["total_score", "status", "name"],
		order_by="modified desc",
	)
	return {
		"score_global": flt(dossier[0], 1) if dossier else None,
		"statut_dossier": dossier[1] if dossier else None,
		"dossier_name": dossier[2] if dossier else None,
	}


# ── SPARKLINES (6 mois) ───────────────────────────────────────────────────────

def _sparklines(company):
	today = nowdate()
	labels, ventes_data, achats_data, tresorerie_data = [], [], [], []

	for i in range(5, -1, -1):
		ref = add_months(today, -i)
		fd  = get_first_day(ref)
		ld  = get_last_day(ref)

		labels.append(frappe.utils.formatdate(fd, "MMM yy"))

		ca = frappe.db.sql("""
			SELECT COALESCE(SUM(grand_total), 0) FROM `tabSales Invoice`
			WHERE company = %s AND docstatus = 1 AND posting_date BETWEEN %s AND %s
		""", (company, fd, ld))[0][0] or 0
		ventes_data.append(flt(ca, 0))

		achats = frappe.db.sql("""
			SELECT COALESCE(SUM(grand_total), 0) FROM `tabPurchase Invoice`
			WHERE company = %s AND docstatus = 1 AND posting_date BETWEEN %s AND %s
		""", (company, fd, ld))[0][0] or 0
		achats_data.append(flt(achats, 0))

		treso = frappe.db.sql("""
			SELECT COALESCE(SUM(debit - credit), 0) FROM `tabGL Entry`
			WHERE company = %s AND account LIKE '5%%' AND is_cancelled = 0 AND posting_date <= %s
		""", (company, ld))[0][0] or 0
		tresorerie_data.append(flt(treso, 0))

	return {
		"labels": labels,
		"ventes": ventes_data,
		"achats": achats_data,
		"tresorerie": tresorerie_data,
	}
