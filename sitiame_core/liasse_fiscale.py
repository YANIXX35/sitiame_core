# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""The "Liasse fiscale" desk tile, for Sitiame staff: the SYSCOHADA versions
of the standard financial statements (balance sheet, income statement, cash
flow as TAFIRE, fixed assets and depreciation schedules), each its own report
on the Liasse SYSCOHADA computations (syscohada_statements.py), next to the
full Excel liasse. ERPNext's own statements stay where they are."""

import frappe
from frappe import _

TILE = "Liasse fiscale"

# report name -> statement of report/liasse_syscohada
STATEMENT_REPORTS = {
	"Bilan actif SYSCOHADA": "Bilan actif",
	"Bilan passif SYSCOHADA": "Bilan passif",
	"Compte de resultat SYSCOHADA": "Compte de résultat",
	"TAFIRE SYSCOHADA": "TAFIRE",
	"Tableau des immobilisations SYSCOHADA": "Tableau 1 — Actif immobilisé",
	"Tableau des amortissements SYSCOHADA": "Tableau 2 — Amortissements",
}

# (label, link type, link to) of the tile's sidebar
SIDEBAR_ITEMS = (
	("Bilan actif", "Report", "Bilan actif SYSCOHADA"),
	("Bilan passif", "Report", "Bilan passif SYSCOHADA"),
	("Compte de résultat", "Report", "Compte de resultat SYSCOHADA"),
	("TAFIRE (flux de trésorerie)", "Report", "TAFIRE SYSCOHADA"),
	("Tableau des immobilisations", "Report", "Tableau des immobilisations SYSCOHADA"),
	("Tableau des amortissements", "Report", "Tableau des amortissements SYSCOHADA"),
	("Balance générale", "Report", "Trial Balance"),
	("Grand livre", "Report", "General Ledger"),
	("Liasse Excel complète", "Page", "erp-comptable"),
)


def staff_only():
	"""The tile is Sitiame staff's: a PME account is refused even if it
	reaches a report by its URL (PME accounts carry Accounts Manager too)."""
	if "PME Client" in frappe.get_roles():
		frappe.throw(_("Réservé au personnel Sitiame."), frappe.PermissionError)


def run_statement(report_name, filters):
	from sitiame_core.sitiame_core.report.liasse_syscohada.liasse_syscohada import execute

	staff_only()
	filters = frappe._dict(filters or {})
	filters.statement = STATEMENT_REPORTS[report_name]
	return execute(filters)
