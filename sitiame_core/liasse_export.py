# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Export des écritures ERPNext vers le modèle Excel « Liasse SYSCOHADA ».

Le modèle (fichiers privés du site, 'liasse_syscohada_template.xlsx') calcule
lui-même balance, grand livre, bilan, compte de résultat, TAFIRE, tableaux
annexes et contrôles à partir de ses feuilles Journal (exercice N) et
Journal_N1 (N-1). L'export y écrit donc les écritures de chaque exercice,
précédées des reports d'ouverture (journal AN, la convention du modèle), et
renseigne PARAMETRES (raison sociale, NIF, dates).

Jusqu'au 2026-10-15 il écrivait des soldes dans la feuille Balance : N-1,
TAFIRE et tableaux annexes restaient vides, les comptes de bilan sans
mouvement sur la période disparaissaient, les charges et produits cumulaient
les exercices précédents, et raison sociale / dates allaient dans des
cellules que la liasse ne lit pas.
"""

import io
import os
import re
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, add_months, date_diff, get_site_path, getdate

TEMPLATE_NAME = "liasse_syscohada_template.xlsx"

# Feuilles Journal / Journal_N1 : A Date, B Journal, C Pièce, D Compte,
# F Libellé, G Débit, H Crédit, I Tiers, J Centre de coût. E et K-P sont des
# formules du modèle, jamais écrites.
FIRST_ROW, LAST_ROW = 2, 20001
DATA_COLUMNS = (1, 2, 3, 4, 6, 7, 8, 9, 10)

OPENING_JOURNAL = "AN"
PROFIT_ACCOUNT, LOSS_ACCOUNT = "1301000", "1309000"  # résultat des exercices antérieurs non clôturés
BALANCE_SHEET_CLASSES = "12345"

VOUCHER_JOURNALS = {
	"Sales Invoice": "VT",
	"POS Invoice": "VT",
	"Purchase Invoice": "AC",
	"Stock Entry": "ST",
	"Purchase Receipt": "ST",
	"Delivery Note": "ST",
	"Stock Reconciliation": "ST",
	"Landed Cost Voucher": "ST",
	"Salary Slip": "PA",
	"Payroll Entry": "PA",
}


# ── comptes ─────────────────────────────────────────────────────────────────

def _extract_account_code(account_name: str) -> str:
	"""'10110 - Capital souscrit - MaPME' → '10110'"""
	m = re.match(r"^(\d+)", (account_name or "").strip())
	return m.group(1) if m else ""


def _normalize_to_7(code: str) -> str:
	"""'10110' → '1011000'  (complété par des zéros à 7 chiffres, ou tronqué)"""
	if not code:
		return ""
	if len(code) >= 7:
		return code[:7]
	return code.ljust(7, "0")


def account_resolver(plan_codes, group_codes):
	"""code ERPNext → code imputable du modèle, ou None. Essaie le code à 7
	chiffres puis le code tel quel (le modèle a des comptes à 3-4 chiffres,
	« 633 »), en raccourcissant jusqu'au compte imputable le plus précis ;
	jamais un compte de regroupement (CTRL_AUX)."""
	usable = {str(code) for code in plan_codes if code} - {str(code) for code in group_codes if code}
	cache = {}

	def resolve(code):
		if code not in cache:
			cache[code] = None
			for length in range(len(code), 1, -1):
				prefix = code[:length]
				match = next((c for c in (_normalize_to_7(prefix), prefix) if c in usable), None)
				if match:
					cache[code] = match
					break
		return cache[code]

	return resolve


# ── écritures ───────────────────────────────────────────────────────────────

def journal_code(voucher_type, account_types, is_opening=False):
	if is_opening:
		return OPENING_JOURNAL
	if voucher_type in VOUCHER_JOURNALS:
		return VOUCHER_JOURNALS[voucher_type]
	if "Bank" in account_types:
		return "BQ"
	if "Cash" in account_types:
		return "CS"
	return "OD"


def build_journal_rows(gl_rows, resolve):
	"""Lignes du Journal à partir des écritures (une par pièce, compte et
	tiers, montant net) -> (lignes, comptes non reconnus)."""
	types_by_voucher = defaultdict(set)
	for row in gl_rows:
		types_by_voucher[row["voucher_no"]].add(row.get("account_type") or "")

	rows, unknown = [], set()
	for row in gl_rows:
		net = float(row.get("debit") or 0) - float(row.get("credit") or 0)
		if abs(net) < 0.005:
			continue
		raw = _extract_account_code(row.get("account_number") or row.get("account") or "")
		code = resolve(raw) if raw else None
		if not code:
			unknown.add(row.get("account") or raw)
			code = _normalize_to_7(raw) or (row.get("account") or "")
		rows.append(
			{
				"date": getdate(row["posting_date"]),
				"journal": journal_code(row["voucher_type"], types_by_voucher[row["voucher_no"]], row.get("is_opening") == "Yes"),
				"piece": row["voucher_no"],
				"account": code,
				"label": (row.get("remarks") or f"{row['voucher_type']} {row['voucher_no']}")[:140],
				"debit": round(max(net, 0), 2),
				"credit": round(max(-net, 0), 2),
				"party": row.get("party") or "",
				"cost_center": row.get("cost_center") or "",
			}
		)
	return rows, unknown


def build_opening_rows(balances, resolve, date):
	"""Reports d'ouverture (journal AN) au premier jour de l'exercice : le
	solde de chaque compte de bilan, et le résultat des exercices antérieurs
	encore en charges/produits (sans clôture d'exercice dans ERPNext) en
	1301000 / 1309000. `balances` : [{account, account_number, balance}]."""
	rows, unknown, result = [], set(), 0.0
	for row in balances:
		balance = float(row.get("balance") or 0)
		if abs(balance) < 0.005:
			continue
		raw = _extract_account_code(row.get("account_number") or row.get("account") or "")
		code = resolve(raw) if raw else None
		klass = (code or raw or "9")[0]
		if klass not in BALANCE_SHEET_CLASSES:
			result += balance
			continue
		if not code:
			unknown.add(row.get("account") or raw)
			code = _normalize_to_7(raw) or (row.get("account") or "")
		rows.append(_opening_row(date, code, balance, _("Report à nouveau")))
	if abs(result) >= 0.005:
		account = LOSS_ACCOUNT if result > 0 else PROFIT_ACCOUNT
		rows.append(_opening_row(date, account, result, _("Résultat des exercices antérieurs")))
	return rows, unknown


def _opening_row(date, account, balance, label):
	return {
		"date": getdate(date),
		"journal": OPENING_JOURNAL,
		"piece": "AN",
		"account": account,
		"label": label,
		"debit": round(max(balance, 0), 2),
		"credit": round(max(-balance, 0), 2),
		"party": "",
		"cost_center": "",
	}


def compact(rows, capacity=LAST_ROW - FIRST_ROW + 1):
	"""Au-delà de la capacité du modèle (20 000 lignes) : cumul par mois,
	journal et compte. Les reports d'ouverture restent détaillés."""
	if len(rows) <= capacity:
		return rows
	totals = {}
	for row in rows:
		if row["journal"] == OPENING_JOURNAL:
			continue
		month = row["date"].replace(day=1)
		key = (month, row["journal"], row["account"])
		total = totals.setdefault(key, {**row, "date": month, "piece": f"{row['journal']}-{month:%Y-%m}", "label": _("Cumul du mois"), "party": "", "cost_center": "", "debit": 0, "credit": 0, "net": 0})
		total["net"] += row["debit"] - row["credit"]
	compacted = [row for row in rows if row["journal"] == OPENING_JOURNAL]
	for total in totals.values():
		net = total.pop("net")
		total.update(debit=round(max(net, 0), 2), credit=round(max(-net, 0), 2))
		compacted.append(total)
	if len(compacted) > capacity:
		frappe.throw(_("Trop d'écritures pour le modèle Excel ({0} lignes, maximum {1}).").format(len(compacted), capacity))
	return compacted


# ── données ERPNext ─────────────────────────────────────────────────────────

def _gl_rows(company, from_date, to_date):
	"""Écritures de la période, hors clôture d'exercice (le modèle calcule le
	résultat lui-même)."""
	return frappe.db.sql(
		"""
		SELECT gle.posting_date, gle.voucher_type, gle.voucher_no, gle.account, a.account_number,
			a.account_type, gle.party, gle.cost_center, MAX(gle.remarks) AS remarks, gle.is_opening,
			SUM(gle.debit) AS debit, SUM(gle.credit) AS credit
		FROM `tabGL Entry` gle
		JOIN `tabAccount` a ON a.name = gle.account
		WHERE gle.company = %(company)s AND gle.is_cancelled = 0
			AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND gle.voucher_type != 'Period Closing Voucher'
		GROUP BY gle.posting_date, gle.voucher_type, gle.voucher_no, gle.account, gle.party, gle.cost_center, gle.is_opening
		ORDER BY gle.posting_date, gle.voucher_no
		""",
		{"company": company, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)


def _balances_before(company, date):
	return frappe.db.sql(
		"""
		SELECT gle.account, a.account_number, SUM(gle.debit) - SUM(gle.credit) AS balance
		FROM `tabGL Entry` gle
		JOIN `tabAccount` a ON a.name = gle.account
		WHERE gle.company = %(company)s AND gle.is_cancelled = 0 AND gle.posting_date < %(date)s
		GROUP BY gle.account
		""",
		{"company": company, "date": date},
		as_dict=True,
	)


def exercise_journal(company, from_date, to_date, resolve):
	opening, unknown_opening = build_opening_rows(_balances_before(company, from_date), resolve, from_date)
	rows, unknown = build_journal_rows(_gl_rows(company, from_date, to_date), resolve)
	return compact(opening + rows), unknown_opening | unknown


def previous_period(from_date, to_date):
	"""N-1 : l'exercice de même durée qui précède."""
	start, end = getdate(from_date), getdate(to_date)
	months = round(date_diff(end, start) / 30.44) or 12
	return getdate(add_months(start, -months)), getdate(add_days(start, -1))


# ── classeur ────────────────────────────────────────────────────────────────

def _get_template_path() -> str:
	path = os.path.join(get_site_path("private", "files"), TEMPLATE_NAME)
	if not os.path.exists(path):
		frappe.throw(
			_("Template Liasse introuvable. Uploadez d'abord le fichier "
			  "'{0}' dans les fichiers privés du site.").format(TEMPLATE_NAME),
			frappe.ValidationError,
		)
	return path


def write_journal(ws, rows):
	"""Efface les lignes d'exemple du modèle puis écrit `rows`."""
	last = FIRST_ROW - 1
	for index, values in enumerate(ws.iter_rows(min_row=FIRST_ROW, max_row=LAST_ROW, max_col=10, values_only=True)):
		if any(values[col - 1] not in (None, "") for col in DATA_COLUMNS):
			last = FIRST_ROW + index
	for r in range(FIRST_ROW, last + 1):
		for col in DATA_COLUMNS:
			ws.cell(r, col).value = None
	for r, row in enumerate(rows, start=FIRST_ROW):
		values = (row["date"], row["journal"], row["piece"], row["account"], row["label"], row["debit"], row["credit"], row["party"], row["cost_center"])
		for col, value in zip(DATA_COLUMNS, values):
			ws.cell(r, col).value = value
		ws.cell(r, 1).number_format = "dd/mm/yyyy"
		ws.cell(r, 4).number_format = "@"


def write_parameters(ws, params):
	"""PARAMETRES!D3..D11, lus par toutes les pages de la liasse."""
	fmt = lambda d: getdate(d).strftime("%d/%m/%Y")  # noqa: E731
	values = {
		"D3": params.get("company_name"),
		"D4": params.get("abbr"),
		"D5": params.get("address"),
		"D6": params.get("tax_id"),
		"D7": fmt(params["to_date"]),
		"D8": params["months"],
		"D9": fmt(params["from_date"]),
		"D10": fmt(params["to_date"]),
		"D11": fmt(params["previous_to_date"]),
	}
	for cell, value in values.items():
		ws[cell] = value


def fill_workbook(wb, rows_n, rows_n1, params):
	write_journal(wb["Journal"], rows_n)
	write_journal(wb["Journal_N1"], rows_n1)
	write_parameters(wb["PARAMETRES"], params)
	# openpyxl n'évalue pas les formules : Excel / LibreOffice recalculent à l'ouverture
	wb.calculation.fullCalcOnLoad = True
	buf = io.BytesIO()
	wb.save(buf)
	return buf.getvalue()


def _company_params(company, from_date, to_date, previous_to):
	row = frappe.db.get_value("Company", company, ["company_name", "abbr", "tax_id"], as_dict=True) or {}
	signup = frappe.db.get_value("Company Signup", {"company": company}, ["address", "city"], as_dict=True) or {}
	months = round(date_diff(getdate(to_date), getdate(from_date)) / 30.44) or 12
	return {
		"company_name": row.get("company_name") or company,
		"abbr": row.get("abbr"),
		"address": ", ".join(x for x in (signup.get("address"), signup.get("city")) if x) or None,
		"tax_id": row.get("tax_id"),
		"from_date": from_date,
		"to_date": to_date,
		"previous_to_date": previous_to,
		"months": months,
	}


# ── validation ───────────────────────────────────────────────────────────────

def _check_balance_equilibre(company: str, from_date: str, to_date: str):
	"""Vérifie débit total = crédit total sur la période.
	Affiche un avertissement orange si l'écart dépasse 1 XOF (arrondi)."""
	row = frappe.db.sql(
		"""
		SELECT
			SUM(debit)            AS total_debit,
			SUM(credit)           AS total_credit,
			ABS(SUM(debit) - SUM(credit)) AS diff
		FROM `tabGL Entry`
		WHERE company = %(company)s
		  AND posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND is_cancelled = 0
		""",
		{"company": company, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)
	if not row or not row[0].total_debit:
		frappe.msgprint(
			_("Aucune écriture pour cette période."),
			indicator="orange",
			title=_("Balance vide"),
		)
		return
	diff = float(row[0].diff or 0)
	if diff > 1:
		frappe.msgprint(
			_(
				"La balance n'est pas équilibrée (écart {0} XOF). "
				"Vérifiez les écritures avant d'utiliser la liasse."
			).format(f"{diff:,.0f}"),
			indicator="orange",
			title=_("Balance déséquilibrée"),
		)


# ── public API ────────────────────────────────────────────────────────────────

def build_liasse(company, from_date, to_date):
	"""-> (contenu xlsx, comptes ERPNext absents du plan du modèle)."""
	import openpyxl

	wb = openpyxl.load_workbook(_get_template_path())
	plan_codes = [row[0] for row in wb["Plan_Comptable"].iter_rows(min_row=2, max_row=1456, min_col=2, max_col=2, values_only=True)]
	group_codes = [row[0] for row in wb["CTRL_AUX"].iter_rows(min_row=2, max_row=304, max_col=1, values_only=True)] if "CTRL_AUX" in wb.sheetnames else []
	resolve = account_resolver(plan_codes, group_codes)

	previous_from, previous_to = previous_period(from_date, to_date)
	rows_n, unknown_n = exercise_journal(company, from_date, to_date, resolve)
	rows_n1, unknown_n1 = exercise_journal(company, previous_from, previous_to, resolve)
	content = fill_workbook(wb, rows_n, rows_n1, _company_params(company, from_date, to_date, previous_to))
	return content, sorted(unknown_n | unknown_n1)


@frappe.whitelist()
def export_liasse(company: str, from_date: str, to_date: str):
	"""Génère le fichier Excel Liasse rempli avec les écritures ERPNext et le
	renvoie en téléchargement direct (réponse binaire)."""
	roles = set(frappe.get_roles())
	if not {"Accounts Manager", "System Manager"} & roles:
		frappe.throw(_("Réservé aux comptables et administrateurs."), frappe.PermissionError)
	# Faille 2026-10-12: any PME has Accounts Manager — verify it owns this company.
	frappe.has_permission("Company", "read", company, throw=True)

	_check_balance_equilibre(company, from_date, to_date)
	xlsx_bytes, unknown = build_liasse(company, from_date, to_date)
	if unknown:
		frappe.log_error(
			title="Liasse : comptes absents du plan du modèle",
			message=f"{company} {from_date}→{to_date} : " + ", ".join(unknown),
		)

	filename = f"Liasse_{company.replace(' ', '_')}_{to_date}.xlsx"
	frappe.response["filename"] = filename
	frappe.response["filecontent"] = xlsx_bytes
	frappe.response["type"] = "binary"
