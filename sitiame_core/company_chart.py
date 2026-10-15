# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Every new company is created on the SYSCOHADA chart with account numbers,
whatever creates it: /company-signup and "Inscrire une PME" already asked
for it (api._provision_company_signup), PME360 (Laravel ErpNextClient) asked
for the chart but never set the default accounts, and a company typed in the
desk got ERPNext's "Standard" chart (KONAN ELIE, 2026-10-07: SYSCOHADA
accounts without numbers, defaults on Debtors/Creditors/Cash). The SYSCOHADA
statements, the liasse and the scanned-invoice import all look accounts up
by number. A company copied from an existing one keeps that company's chart."""

import frappe

# api.SYSCOHADA_CHART_OF_ACCOUNTS (api.py is not imported here: hooks load
# this module for every Company save)
SYSCOHADA_CHART = "Syscohada - Plan Comptable avec code"


def force_syscohada_chart(doc, method=None):
	"""Company before_insert."""
	if doc.get("create_chart_of_accounts_based_on") == "Existing Company" and doc.get("existing_company"):
		return
	doc.create_chart_of_accounts_based_on = "Standard Template"
	doc.chart_of_accounts = SYSCOHADA_CHART


def set_syscohada_defaults(doc, method=None):
	"""Company on_update, once ERPNext has built the chart (on_update of a
	new Company): default receivable, payable, cash, income, expense...
	accounts by SYSCOHADA number, and the 18% VAT templates."""
	if not doc.flags.in_insert or doc.get("chart_of_accounts") != SYSCOHADA_CHART:
		return
	from sitiame_core.api import _apply_syscohada_defaults

	_apply_syscohada_defaults(doc.name)
