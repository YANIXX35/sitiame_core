# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Document numbers of each PME, continuous per company and per fiscal year:
FV-SYSTE-2026-00001, FV-SYSTE-2026-00002... ERPNext's series (ACC-SINV-
2026-.....) are shared by every company of the site: a PME's first invoice
was number 00002 because SITIAME had used 00001, and each PME's sequence had
the holes of the others (cloisonnement audit D4, 2026-10-15).

Frappe's Document Naming Rule, one per (doctype, company, fiscal year),
matched on the company and the document date; each rule keeps its own
counter. Rules are ensured for every company and fiscal year at migration,
and when a company or a fiscal year is created. Documents already numbered
keep their name; amendments keep ERPNext's "-1" suffix."""

import frappe

# doctype -> (prefix, date field)
NUMBERED_DOCTYPES = {
	"Sales Invoice": ("FV", "posting_date"),
	"Purchase Invoice": ("FA", "posting_date"),
	"Payment Entry": ("REG", "posting_date"),
	"Journal Entry": ("OD", "posting_date"),
	"Quotation": ("DEV", "transaction_date"),
	"Sales Order": ("CDE", "transaction_date"),
	"Delivery Note": ("BL", "posting_date"),
	"Purchase Order": ("BC", "transaction_date"),
	"Purchase Receipt": ("BR", "posting_date"),
	"Stock Entry": ("MVT", "posting_date"),
	"Material Request": ("DA", "transaction_date"),
}
PREFIX_DIGITS = 5
PRIORITY = 10


def rule_prefix(prefix, abbr, year):
	return f"{prefix}-{abbr}-{year}-"


def rule_spec(doctype, company, abbr, fiscal_year):
	"""The Document Naming Rule a (doctype, company, fiscal year) needs."""
	prefix, date_field = NUMBERED_DOCTYPES[doctype]
	start, end, year = fiscal_year
	return {
		"doctype": "Document Naming Rule",
		"document_type": doctype,
		"prefix": rule_prefix(prefix, abbr, year),
		"prefix_digits": PREFIX_DIGITS,
		"priority": PRIORITY,
		"conditions": [
			{"field": "company", "condition": "=", "value": company},
			{"field": date_field, "condition": ">=", "value": str(start)},
			{"field": date_field, "condition": "<=", "value": str(end)},
		],
	}


def _year_label(name, start):
	"""The fiscal year's name when it is a year ("2026"), else its first year:
	a name such as "2025-2026" or "2025/26" must not end up in document names."""
	return name if str(name).isdigit() else str(frappe.utils.getdate(start).year)


def _fiscal_years():
	return [
		(row.year_start_date, row.year_end_date, _year_label(row.name, row.year_start_date))
		for row in frappe.get_all("Fiscal Year", filters={"disabled": 0}, fields=["name", "year_start_date", "year_end_date"])
	]


def ensure_rules(companies=None, fiscal_years=None):
	"""Creates the missing rules; returns how many were created."""
	companies = companies or frappe.get_all("Company", pluck="name")
	fiscal_years = fiscal_years or _fiscal_years()
	created = 0
	for company in companies:
		abbr = frappe.db.get_value("Company", company, "abbr")
		if not abbr:
			continue
		for fiscal_year in fiscal_years:
			for doctype in NUMBERED_DOCTYPES:
				if not frappe.db.exists("DocType", doctype):
					continue
				spec = rule_spec(doctype, company, abbr, fiscal_year)
				if frappe.db.exists("Document Naming Rule", {"document_type": doctype, "prefix": spec["prefix"]}):
					continue
				# system configuration, created at migration or with the company
				frappe.get_doc(spec).insert(ignore_permissions=True)
				created += 1
	return created


def on_company_update(doc, method=None):
	"""Company on_update: a new company gets its numbering at once."""
	if doc.flags.in_insert:
		ensure_rules(companies=[doc.name])


def on_fiscal_year_update(doc, method=None):
	"""Fiscal Year on_update: every company gets the new year's numbering."""
	if not doc.disabled:
		ensure_rules(fiscal_years=[(doc.year_start_date, doc.year_end_date, _year_label(doc.name, doc.year_start_date))])
