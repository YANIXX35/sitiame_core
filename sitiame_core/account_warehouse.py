# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""One warehouse per PME account. Each account runs its own activity
(liasse_scope.py), so its stock -- quantities and valuation -- must not mix
with the other accounts of its company (2026-10-16). The company's first
account keeps the company's own warehouse ("Magasins"), where its stock
already is; every other account gets "Magasin <name>".

The mapping is a User Permission on Warehouse applicable to the Warehouse
doctype only: it limits the warehouse pickers to the account's own, without
the strict user permissions hiding every service invoice with no warehouse.
The account's warehouse is then filled in on its stock documents, another
account's is refused, and the stock reports are narrowed to it."""

import frappe
from frappe import _

# stock documents: header warehouse fields, then item rows' fields
STOCK_DOCTYPES = {
	"Sales Invoice": ("set_warehouse",),
	"POS Invoice": ("set_warehouse",),
	"Delivery Note": ("set_warehouse",),
	"Sales Order": ("set_warehouse",),
	"Purchase Invoice": ("set_warehouse",),
	"Purchase Receipt": ("set_warehouse",),
	"Purchase Order": ("set_warehouse",),
	"Material Request": ("set_warehouse",),
	"Stock Reconciliation": ("set_warehouse",),
	"Stock Entry": ("from_warehouse", "to_warehouse"),
}
ROW_FIELDS = ("warehouse", "s_warehouse", "t_warehouse", "target_warehouse", "from_warehouse")

# stock reports narrowed to the account's warehouse (filter -> list or one)
STOCK_REPORTS = {
	"erpnext.stock.report.stock_balance.stock_balance": True,
	"erpnext.stock.report.stock_ledger.stock_ledger": True,
	"erpnext.stock.report.stock_projected_qty.stock_projected_qty": False,
}


def _pme_company(user):
	from sitiame_core.liasse_scope import _company, liasse_owner

	return _company(user) if liasse_owner(user) else None


def _mapped(user):
	return frappe.db.get_value(
		"User Permission", {"user": user, "allow": "Warehouse", "applicable_for": "Warehouse"}, "for_value"
	)


def _primary_account(company):
	"""The account that signed the company up, else its oldest account."""
	signup = frappe.db.get_value("Company Signup", {"company": company}, "email")
	if signup and frappe.db.exists("User Permission", {"user": signup, "allow": "Company", "for_value": company}):
		return signup
	return frappe.db.get_value(
		"User Permission", {"allow": "Company", "for_value": company}, "user", order_by="creation asc"
	)


def _company_warehouse(company):
	from sitiame_core.onboarding import _warehouse

	return _warehouse(company)


def _new_warehouse(company, user):
	full_name = frappe.db.get_value("User", user, "full_name") or user.split("@")[0]
	parent = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 1}, "name", order_by="lft asc"
	)
	base = f"Magasin {full_name}"[:100]
	label, n = base, 2
	abbr = frappe.get_cached_value("Company", company, "abbr")
	while frappe.db.exists("Warehouse", f"{label} - {abbr}"):
		label, n = f"{base} {n}", n + 1
	doc = frappe.get_doc(
		{"doctype": "Warehouse", "warehouse_name": label, "company": company, "parent_warehouse": parent}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def account_warehouse(user=None):
	"""The PME account's warehouse, created and mapped on first use; None
	for staff or an account without a company."""
	user = user or frappe.session.user
	company = _pme_company(user)
	if not company:
		return None
	warehouse = _mapped(user)
	if warehouse and frappe.db.get_value("Warehouse", warehouse, "company") == company:
		return warehouse
	if _primary_account(company) == user:
		warehouse = _company_warehouse(company)
	else:
		warehouse = _new_warehouse(company, user)
	if not warehouse:
		return None
	frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": user,
			"allow": "Warehouse",
			"for_value": warehouse,
			"apply_to_all_doctypes": 0,
			"applicable_for": "Warehouse",
			"is_default": 1,
		}
	).insert(ignore_permissions=True)
	return warehouse


def _others(company, user):
	"""Warehouses of the company given to its other accounts."""
	return set(
		frappe.get_all(
			"User Permission",
			{"allow": "Warehouse", "applicable_for": "Warehouse", "user": ["!=", user]},
			pluck="for_value",
		)
	) & set(frappe.get_all("Warehouse", {"company": company}, pluck="name"))


def set_account_warehouse(doc, method=None):
	"""before_validate: the account's warehouse where none is set; another
	account's warehouse is refused."""
	user = frappe.session.user
	warehouse = account_warehouse(user)
	if not warehouse:
		return
	header = STOCK_DOCTYPES.get(doc.doctype, ())
	if doc.doctype == "Stock Entry":
		# receipt -> into the account's warehouse, issue -> out of it
		side = {"Material Receipt": "to_warehouse", "Material Issue": "from_warehouse"}.get(doc.get("purpose"))
		if side and not doc.get(side):
			doc.set(side, warehouse)
			row_field = "t_warehouse" if side == "to_warehouse" else "s_warehouse"
			for row in doc.get("items") or []:
				row.set(row_field, row.get(row_field) or warehouse)
	elif header:
		if not doc.get(header[0]):
			doc.set(header[0], warehouse)
		for row in doc.get("items") or []:
			if row.get("item_code") and not row.get("warehouse") and frappe.get_cached_value(
				"Item", row.item_code, "is_stock_item"
			):
				row.warehouse = doc.get(header[0])
	others = _others(doc.company, user)
	used = {doc.get(f) for f in header} | {row.get(f) for row in doc.get("items") or [] for f in ROW_FIELDS}
	refused = sorted(used & others)
	if refused:
		frappe.throw(
			_("Le magasin {0} appartient à un autre compte de la société. Utilisez le vôtre : {1}.").format(
				", ".join(refused), warehouse
			),
			frappe.PermissionError,
		)


def _narrow(filters, as_list):
	warehouse = account_warehouse()
	if not warehouse:
		return filters
	filters = frappe._dict(filters or {})
	filters.warehouse = [warehouse] if as_list else warehouse
	return filters


def patch_stock_reports():
	"""before_request / before_job: each stock report reads only the PME
	account's warehouse (they ignore permission conditions)."""
	import importlib

	for module_name, as_list in STOCK_REPORTS.items():
		module = importlib.import_module(module_name)
		if getattr(module.execute, "_sitiame_guarded", False):
			continue
		original = module.execute

		def execute(filters=None, _original=original, _as_list=as_list):
			return _original(_narrow(filters, _as_list))

		execute._sitiame_guarded = True
		module.execute = execute


def on_company_permission(doc, method=None):
	"""User Permission after_insert: a new PME account gets its warehouse."""
	if doc.allow == "Company" and "PME Client" in frappe.get_roles(doc.user):
		account_warehouse(doc.user)


def backfill():
	"""after_migrate: every PME account gets its warehouse."""
	for row in frappe.get_all("User Permission", {"allow": "Company"}, ["user"]):
		if "PME Client" in frappe.get_roles(row.user) and not _mapped(row.user):
			account_warehouse(row.user)
	frappe.db.commit()
