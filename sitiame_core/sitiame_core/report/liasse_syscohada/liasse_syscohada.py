# Copyright (c) 2026, Sitiame Capital
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt

from sitiame_core.syscohada_statements import (
	ACTIF_LINES,
	PASSIF_LINES,
	RESULTAT_ORDER,
	RESULTAT_RULES,
	RESULTAT_TOTALS,
	compute_statements,
	fiscal_year_dates,
	previous_fiscal_year,
)

STATEMENTS = ("Bilan actif", "Bilan passif", "Compte de résultat")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company or not filters.fiscal_year:
		return [], []
	# The report's own role check doesn't cover which company is read:
	# enforce the user's Company permission (PME accounts see only theirs).
	frappe.has_permission("Company", "read", filters.company, throw=True)

	statement = filters.statement or STATEMENTS[0]
	start, end = fiscal_year_dates(filters.fiscal_year)
	current = compute_statements(filters.company, start, end)

	previous = None
	previous_year = previous_fiscal_year(filters.fiscal_year)
	if previous_year:
		p_start, p_end = fiscal_year_dates(previous_year)
		previous = compute_statements(filters.company, p_start, p_end)

	if statement == "Bilan actif":
		columns, data = _actif(current, previous)
	elif statement == "Bilan passif":
		columns, data = _passif(current, previous)
	else:
		columns, data = _resultat(current, previous)

	return columns, data, _message(current), None, _summary(current)


def _money(fieldname, label):
	return {"fieldname": fieldname, "label": label, "fieldtype": "Currency", "width": 160}


def _ref_columns():
	return [
		{"fieldname": "ref", "label": _("Réf."), "fieldtype": "Data", "width": 70},
		{"fieldname": "libelle", "label": _("Libellé"), "fieldtype": "Data", "width": 380},
	]


def _row(code, label, is_total, **amounts):
	return {
		"ref": "" if code.startswith("T") and "_" in code else code,
		"libelle": label,
		"bold": 1 if is_total else 0,
		"indent": 0 if is_total else 1,
		**{key: flt(value) for key, value in amounts.items()},
	}


def _actif(current, previous):
	columns = _ref_columns() + [
		_money("brut", _("Brut")),
		_money("amort", _("Amort. et dépréc.")),
		_money("net", _("Net N")),
		_money("net_n1", _("Net N-1")),
	]
	data = []
	for code, label, *parts in ACTIF_LINES:
		data.append(
			_row(
				code,
				label,
				bool(parts),
				brut=current["actif"][code]["brut"],
				amort=current["actif"][code]["amort"],
				net=current["actif_net"][code],
				net_n1=previous["actif_net"][code] if previous else 0,
			)
		)
	return columns, data


def _passif(current, previous):
	columns = _ref_columns() + [_money("net", _("Net N")), _money("net_n1", _("Net N-1"))]
	data = [
		_row(
			code,
			label,
			bool(parts),
			net=current["passif"][code],
			net_n1=previous["passif"][code] if previous else 0,
		)
		for code, label, *parts in PASSIF_LINES
	]
	return columns, data


def _resultat(current, previous):
	columns = _ref_columns() + [_money("net", _("Exercice N")), _money("net_n1", _("Exercice N-1"))]
	labels = {code: label for code, label, *_rest in RESULTAT_RULES}
	totals = {code: label for code, label, _formula in RESULTAT_TOTALS}
	data = []
	for code in RESULTAT_ORDER:
		data.append(
			_row(
				code,
				totals.get(code) or labels[code],
				code in totals,
				net=current["resultat"][code],
				net_n1=previous["resultat"][code] if previous else 0,
			)
		)
	return columns, data


def _summary(current):
	gap = flt(current["total_actif"] - current["total_passif"])
	return [
		{"value": current["total_actif"], "label": _("Total actif"), "datatype": "Currency"},
		{"value": current["total_passif"], "label": _("Total passif"), "datatype": "Currency"},
		{"value": current["resultat"]["XZ"], "label": _("Résultat net"), "datatype": "Currency",
		 "indicator": "Green" if current["resultat"]["XZ"] >= 0 else "Red"},
		{"value": gap, "label": _("Écart actif - passif"), "datatype": "Currency",
		 "indicator": "Green" if abs(gap) < 1 else "Red"},
	]


def _message(current):
	notes = []
	if current["unclassified"]:
		notes.append(
			_("Comptes non rattachés à un poste (à vérifier) : {0}").format(
				", ".join(f"{number} ({flt(balance):,.0f})" for number, balance in current["unclassified"])
			)
		)
	if current["unnumbered"]:
		notes.append(
			_("Comptes sans numéro, ignorés : {0}").format(", ".join(current["unnumbered"]))
		)
	return "<br>".join(frappe.utils.escape_html(n) for n in notes) or None
