# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""ERPNext's standard statements (Balance Sheet, Profit and Loss Statement,
Cash Flow) laid out as the SYSCOHADA liasse: one Financial Report Template
each, whose lines are "Custom API" rows answered from the liasse computations
(syscohada_statements.py). The report page preselects the template for a
company on a numbered chart (public/js/syscohada_statements.js); the user
can still clear it to get ERPNext's own layout."""

import frappe
from frappe import _
from frappe.utils import cint, getdate

from sitiame_core.syscohada_statements import (
	ACTIF_LINES,
	PASSIF_LINES,
	RESULTAT_ORDER,
	RESULTAT_RULES,
	RESULTAT_TOTALS,
	compute_statements,
	compute_tafire,
)

API = "sitiame_core.syscohada_templates.line"

# standard report -> its SYSCOHADA template
TEMPLATES = {
	"Balance Sheet": "Bilan SYSCOHADA",
	"Profit and Loss Statement": "Compte de résultat SYSCOHADA",
	"Cash Flow": "TAFIRE SYSCOHADA",
}

# TAFIRE lines as compute_tafire() returns them; "" is a part title.
TAFIRE_LINES = [
	("", _("PARTIE 1 — SOLDES FINANCIERS DE SYNTHÈSE"), True),
	("TD", _("Excédent Brut d'Exploitation (EBE)"), False),
	("UB", _("(-) Frais financiers et charges assimilées"), False),
	("VB", _("(-) Charges HAO décaissables"), False),
	("WA", _("(-) Participation des travailleurs"), False),
	("WB", _("(-) Impôts sur le résultat"), False),
	("RJ", _("(+) Transferts de charges d'exploitation"), False),
	("UA", _("(+) Revenus financiers et produits assimilés"), False),
	("VA", _("(+) Produits HAO encaissables"), False),
	("CAFG", _("CAPACITÉ D'AUTOFINANCEMENT GLOBALE (CAFG)"), True),
	("DIV", _("(-) Distributions de dividendes"), False),
	("AF", _("AUTOFINANCEMENT (AF)"), True),
	("EC", _("Variation globale nette des stocks (N − N-1)"), False),
	("ED", _("Variation globale nette des créances (N − N-1)"), False),
	("EF", _("Variation globale nette des dettes (N − N-1)"), False),
	("XC", _("VARIATION DU B.F.E."), True),
	("TQ", _("Excédent Brut d'Exploitation (rappel)"), False),
	("TR", _("(-/+) Variation du B.F.E."), False),
	("TF", _("(-) Production immobilisée"), False),
	("XD", _("EXCÉDENT DE TRÉSORERIE D'EXPLOITATION (ETE)"), True),
	("", _("PARTIE 2 — TABLEAU EMPLOIS / RESSOURCES"), True),
	("FA", _("I. Charges immobilisées"), False),
	("FB", _("I. Immobilisations incorporelles"), False),
	("FC", _("I. Immobilisations corporelles"), False),
	("FD", _("I. Immobilisations financières"), False),
	("FF", _("INVESTISSEMENT TOTAL (I)"), True),
	("FG", _("II. Variation du BFE"), False),
	("FH", _("A — EMPLOIS ÉCONOMIQUES (FF + II)"), True),
	("FI", _("III. Emplois / Ressources HAO"), False),
	("FJ", _("IV. Remboursements d'emprunts et dettes financières"), False),
	("FK", _("B — EMPLOIS TOTAUX À FINANCER (A + III + IV)"), True),
	("FL", _("V. Dividendes / CAFG"), False),
	("FM", _("VI. Augmentations de capital par apports nouveaux"), False),
	("FN", _("VI. Subventions d'investissement"), False),
	("FP", _("VI. Prélèvements sur le capital"), False),
	("FQ", _("VII. Emprunts nouveaux"), False),
	("FR", _("VII. Autres dettes financières"), False),
	("FS", _("C — RESSOURCES NETTES DE FINANCEMENT"), True),
	("FT", _("D — EXCÉDENT (+) / INSUFFISANCE (−) DE RESSOURCES (C − B)"), True),
	("FU", _("Trésorerie nette à la clôture"), False),
	("FV", _("Trésorerie nette à l'ouverture"), False),
	("FW", _("VARIATION DE LA TRÉSORERIE (FU − FV)"), True),
]


def _line(code, label, bold, prefix):
	ref = "" if "_" in code else code  # TA_ACTIF / TP_PASSIF: no liasse ref
	return {
		"reference_code": f"{prefix}_{code}",
		"display_name": f"{ref}  {label}" if ref else label,
		"data_source": "Custom API",
		"calculation_formula": API,
		"indentation_level": 0 if bold else 1,
		"bold_text": 1 if bold else 0,
		"fieldtype": "Currency",
	}


def _section(label):
	return {"data_source": "Section Break", "display_name": label}


def template_rows(report):
	if report == "Balance Sheet":
		return (
			[_section(_("ACTIF"))]
			+ [_line(code, label, bool(parts), "A") for code, label, *parts in ACTIF_LINES]
			+ [_section(_("PASSIF"))]
			+ [_line(code, label, bool(parts), "P") for code, label, *parts in PASSIF_LINES]
		)
	if report == "Profit and Loss Statement":
		labels = {code: label for code, label, *_rest in RESULTAT_RULES}
		totals = {code: label for code, label, _formula in RESULTAT_TOTALS}
		return [_line(code, totals.get(code) or labels[code], code in totals, "R") for code in RESULTAT_ORDER]
	return [_section(label) if not ref else _line(ref, label, bold, "T") for ref, label, bold in TAFIRE_LINES]


def ensure_templates():
	"""after_migrate: (re)write the three templates from the liasse lines."""
	for report, name in TEMPLATES.items():
		if frappe.db.exists("Financial Report Template", name):
			doc = frappe.get_doc("Financial Report Template", name)
			doc.rows = []
		else:
			doc = frappe.new_doc("Financial Report Template")
			doc.template_name = name
		doc.report_type = report
		doc.disabled = 0
		for row in template_rows(report):
			doc.append("rows", row)
		doc.flags.ignore_permissions = True
		doc.save() if not doc.is_new() else doc.insert()
	frappe.db.commit()


def _cached(key, compute):
	from sitiame_core.liasse_scope import liasse_owner

	cache = getattr(frappe.local, "sitiame_syscohada_cache", None)
	if cache is None:
		cache = frappe.local.sitiame_syscohada_cache = {}
	key = (liasse_owner(), *key)  # each PME account has its own liasse
	if key not in cache:
		cache[key] = compute()
	return cache[key]


def _year_start(company, date):
	from erpnext.accounts.utils import get_fiscal_year

	return getdate(get_fiscal_year(date, company=company)[1])


@frappe.whitelist(methods=["GET", "POST"])
def line(filters=None, periods=None, row=None):
	"""Custom API row: the liasse amount of one line, for each period."""
	filters = frappe._dict(filters or {})
	company = filters.company
	frappe.has_permission("Company", "read", company, throw=True)
	prefix, code = row.get("reference_code").split("_", 1)

	values = []
	for period in periods or []:
		period = frappe._dict(period)
		to_date = getdate(period.to_date)
		if prefix == "T":
			from_date = getdate(period.from_date)
			tafire = _cached(("T", company, from_date, to_date), lambda: compute_tafire(company, from_date, to_date))
			match = next((r for r in tafire["rows"] if r["ref"] == code), None)
			values.append(match["ressources"] - match["emplois"] if match else 0.0)
			continue

		year_start = _year_start(company, to_date)
		from_date = year_start
		if prefix == "R" and filters.get("accumulated_values") is not None and not cint(filters.accumulated_values):
			from_date = getdate(period.from_date)
		stmts = _cached(("S", company, from_date, to_date), lambda: compute_statements(company, from_date, to_date))
		if prefix == "A":
			values.append(stmts["actif_net"][code])
		elif prefix == "P":
			values.append(stmts["passif"][code])
		else:
			values.append(stmts["resultat"][code])
	return values


@frappe.whitelist()
def default_template(report, company=None):
	"""Template the report page preselects: the SYSCOHADA one when the
	company's chart carries account numbers (a chart without them, like
	KONAN ELIE's, keeps ERPNext's layout)."""
	name = TEMPLATES.get(report)
	if not name or not company or not frappe.db.exists("Financial Report Template", name):
		return None
	numbered = frappe.db.exists("Account", {"company": company, "account_number": ["like", "4%"]})
	return name if numbered else None
