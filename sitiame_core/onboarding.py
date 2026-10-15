# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Account setup ("Configuration du compte") shown to a PME until its
starting position is in the books: products and services, opening stock,
receivables, payables and cash. Each opening is posted against the temporary
opening account (4751 on the SYSCOHADA chart), as ERPNext's own opening
tools do, so the liasse starts from real figures. A step the PME has nothing
for ("Je n'en ai pas") is recorded on the Company and counts as done."""

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

SKIPPED_FIELD = "sitiame_onboarding_skipped"
# user default: a staff account sees the window as a demo (nothing saved)
PREVIEW_DEFAULT = "sitiame_onboarding_preview"

STEPS = (
	("produits", _("Créer les produits/services")),
	("stocks", _("Enregistrer les stocks disponibles")),
	("creances", _("Enregistrer les créances en cours")),
	("dettes", _("Enregistrer les dettes en cours")),
	("tresorerie", _("Enregistrer le solde de votre trésorerie (caisse + banque + autres cash disponibles)")),
)
SKIPPABLE = frozenset(["stocks", "creances", "dettes", "tresorerie"])

# cash line -> account number on the SYSCOHADA chart
CASH_ACCOUNTS = (("caisse", "5711"), ("banque", "5211"), ("mobile_money", "552"))


def _company():
	"""The PME's company; staff and Administrator have none here."""
	if frappe.session.user == "Administrator" or "PME Client" not in frappe.get_roles():
		return None
	from sitiame_core.subscription_api import get_user_company

	return get_user_company()


def _own_company():
	company = _company()
	if not company:
		frappe.throw(_("Configuration réservée aux comptes PME rattachés à une société."), frappe.PermissionError)
	return company


def _company_users(company):
	return frappe.get_all("User Permission", {"allow": "Company", "for_value": company}, pluck="user")


def _skipped(company):
	try:
		return set(json.loads(frappe.db.get_value("Company", company, SKIPPED_FIELD) or "[]"))
	except ValueError:
		return set()


def _done(company):
	users = _company_users(company) or [""]
	return {
		"produits": bool(frappe.db.exists("Item", {"owner": ["in", users], "disabled": 0})),
		"stocks": bool(
			frappe.db.exists("Stock Reconciliation", {"company": company, "purpose": "Opening Stock", "docstatus": 1})
		),
		"creances": bool(frappe.db.exists("Sales Invoice", {"company": company, "is_opening": "Yes", "docstatus": 1})),
		"dettes": bool(frappe.db.exists("Purchase Invoice", {"company": company, "is_opening": "Yes", "docstatus": 1})),
		"tresorerie": bool(
			frappe.db.exists(
				"Journal Entry", {"company": company, "voucher_type": "Opening Entry", "docstatus": 1}
			)
		),
	}


@frappe.whitelist()
def get_status():
	"""Steps and their state for the current PME account; show=False for
	staff, or once every step is done or declared empty."""
	company = _company()
	if not company:
		if frappe.session.user != "Administrator" and frappe.defaults.get_user_default(PREVIEW_DEFAULT) == "1":
			return {
				"show": True,
				"preview": True,
				"company": _("Aperçu — rien n'est enregistré"),
				"steps": [{"key": key, "label": label, "state": "todo"} for key, label in STEPS],
				"date": nowdate(),
			}
		return {"show": False}
	done = _done(company)
	skipped = _skipped(company)
	steps = [
		{"key": key, "label": label, "state": "done" if done[key] else "skipped" if key in skipped else "todo"}
		for key, label in STEPS
	]
	return {
		"show": any(s["state"] == "todo" for s in steps),
		"company": company,
		"steps": steps,
		"date": nowdate(),
	}


def set_preview(user, enabled=True):
	"""bench execute: show the window to a staff account as a demo."""
	if enabled:
		frappe.defaults.set_user_default(PREVIEW_DEFAULT, "1", user)
	else:
		frappe.defaults.clear_user_default(PREVIEW_DEFAULT, user)
	frappe.db.commit()


@frappe.whitelist(methods=["POST"])
def skip_step(step):
	"""'Je n'en ai pas': the PME has nothing to declare for this step."""
	if step not in SKIPPABLE:
		frappe.throw(_("Étape inconnue."))
	company = _own_company()
	skipped = _skipped(company) | {step}
	frappe.db.set_value("Company", company, SKIPPED_FIELD, json.dumps(sorted(skipped)), update_modified=False)
	return get_status()


def _rows(rows):
	if isinstance(rows, str):
		rows = json.loads(rows)
	return [frappe._dict(r) for r in rows or []]


def _temporary_account(company):
	from erpnext.accounts.doctype.opening_invoice_creation_tool.opening_invoice_creation_tool import (
		get_temporary_opening_account,
	)

	return get_temporary_opening_account(company)


def _item_code(name, company):
	code = name.strip()
	if not frappe.db.exists("Item", code):
		return code
	abbr = frappe.get_cached_value("Company", company, "abbr")
	code = f"{name.strip()} - {abbr}"
	n = 2
	while frappe.db.exists("Item", code):
		code = f"{name.strip()} - {abbr} {n}"
		n += 1
	return code


@frappe.whitelist(methods=["POST"])
def save_products(rows):
	company = _own_company()
	created = []
	for row in _rows(rows):
		if not (row.item_name or "").strip():
			continue
		stocked = bool(int(row.is_stock_item or 0))
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": _item_code(row.item_name, company),
				"item_name": row.item_name.strip(),
				"item_group": "Products" if stocked else "Services",
				"stock_uom": frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos",
				"is_stock_item": 1 if stocked else 0,
				"include_item_in_manufacturing": 0,
				"standard_rate": flt(row.rate),
			}
		)
		item.insert()
		created.append(item.name)
	if not created:
		frappe.throw(_("Ajoutez au moins un produit ou service."))
	return {"created": created, "status": get_status()}


def _warehouse(company):
	for name in ("Magasins", "Stores"):
		warehouse = frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": name, "is_group": 0})
		if warehouse:
			return warehouse
	return frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 0, "warehouse_type": ["!=", "Transit"]}, "name"
	)


@frappe.whitelist(methods=["POST"])
def save_stock(rows, posting_date=None):
	company = _own_company()
	warehouse = _warehouse(company)
	items = [r for r in _rows(rows) if r.item_code and flt(r.qty) > 0]
	if not items:
		frappe.throw(_("Ajoutez au moins un article avec une quantité."))
	doc = frappe.get_doc(
		{
			"doctype": "Stock Reconciliation",
			"company": company,
			"purpose": "Opening Stock",
			"set_posting_time": 1,
			"posting_date": getdate(posting_date or nowdate()),
			"expense_account": _temporary_account(company),
			"items": [
				{
					"item_code": r.item_code,
					"warehouse": warehouse,
					"qty": flt(r.qty),
					"valuation_rate": flt(r.valuation_rate),
				}
				for r in items
			],
		}
	)
	doc.insert()
	doc.submit()
	return {"name": doc.name, "status": get_status()}


def _opening_invoices(company, party_type, rows, posting_date):
	"""Opening invoices built like ERPNext's Opening Invoice Creation Tool,
	but all or nothing: an error is shown, not logged away."""
	temporary = _temporary_account(company)
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	sales = party_type == "Customer"
	names = []
	for row in rows:
		if not row.party or flt(row.amount) <= 0:
			continue
		date = getdate(row.posting_date or posting_date or nowdate())
		doc = frappe.get_doc(
			{
				"doctype": "Sales Invoice" if sales else "Purchase Invoice",
				"company": company,
				frappe.scrub(party_type): row.party,
				"is_opening": "Yes",
				"set_posting_time": 1,
				"posting_date": date,
				"due_date": getdate(row.due_date) if row.due_date else date,
				"update_stock": 0,
				"is_pos": 0,
				"disable_rounded_total": 1,
				"cost_center": cost_center,
				"remarks": row.reference or _("Solde d'ouverture"),
				**({} if sales else {"bill_no": row.reference, "bill_date": date}),
				"items": [
					{
						"item_name": _("Solde d'ouverture"),
						"description": row.reference or _("Solde d'ouverture"),
						"uom": frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos",
						"qty": 1,
						"rate": flt(row.amount),
						"conversion_factor": 1,
						("income_account" if sales else "expense_account"): temporary,
						"cost_center": cost_center,
					}
				],
			}
		)
		doc.flags.ignore_mandatory = True
		doc.flags.dont_auto_add_taxes = True
		doc.insert()
		doc.submit()
		names.append(doc.name)
	if not names:
		frappe.throw(_("Ajoutez au moins une ligne avec un montant."))
	return names


@frappe.whitelist(methods=["POST"])
def save_receivables(rows, posting_date=None):
	company = _own_company()
	return {"created": _opening_invoices(company, "Customer", _rows(rows), posting_date), "status": get_status()}


@frappe.whitelist(methods=["POST"])
def save_payables(rows, posting_date=None):
	company = _own_company()
	return {"created": _opening_invoices(company, "Supplier", _rows(rows), posting_date), "status": get_status()}


def _cash_account(company, number):
	account = frappe.db.get_value("Account", {"company": company, "account_number": number, "is_group": 0}, "name")
	if account:
		return account
	# chart without numbers (ERPNext "Standard"): the company's cash / a bank account
	if number == "5211":
		return frappe.db.get_value("Account", {"company": company, "account_type": "Bank", "is_group": 0}, "name")
	return frappe.get_cached_value("Company", company, "default_cash_account")


@frappe.whitelist(methods=["POST"])
def save_cash(amounts, posting_date=None):
	company = _own_company()
	if isinstance(amounts, str):
		amounts = json.loads(amounts)
	amounts = amounts or {}
	lines = []
	for key, number in CASH_ACCOUNTS:
		amount = flt(amounts.get(key))
		if amount <= 0:
			continue
		account = _cash_account(company, number)
		if not account:
			frappe.throw(_("Compte {0} introuvable dans le plan comptable.").format(number))
		lines.append({"account": account, "debit_in_account_currency": amount})
	total = sum(line["debit_in_account_currency"] for line in lines)
	if not total:
		frappe.throw(_("Saisissez au moins un montant."))
	lines.append({"account": _temporary_account(company), "credit_in_account_currency": total})
	doc = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Opening Entry",
			"is_opening": "Yes",
			"company": company,
			"posting_date": getdate(posting_date or nowdate()),
			"user_remark": _("Solde d'ouverture de la trésorerie"),
			"accounts": lines,
		}
	)
	doc.insert()
	doc.submit()
	return {"name": doc.name, "status": get_status()}
