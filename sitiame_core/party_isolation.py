# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""A PME account only sees its own customers, suppliers, contacts and
addresses (audit 2026-10-01: every PME read every other one's).

These doctypes have no company in ERPNext, so the PME's Company User
Permission never applied to them. A "company" Link field is added to each:
the Company User Permission then applies natively, read and write, and
since apply_strict_user_permissions is on, a record without a company is
hidden from every PME. Staff, chargés d'affaires, analysts, the PME360 API
account and Administrator have no Company User Permission: untouched.

The field is named "company" because PME360 already sends it when it
creates a PME's customer (ErpNextClient::findOrCreateCustomerForPme).

Items are deliberately left out: PME360 shares one Item between PMEs
(ErpNextClient::findOrCreateItem codes it from the label alone)."""

import frappe

PARTY_DOCTYPES = ("Customer", "Supplier", "Contact", "Address")
COMPANY_FIELD = "company"
SITIAME_COMPANY = "SITIAME"
# acts on behalf of the PMEs: what it creates without a company is left
# without one (hidden from every PME) rather than given to SITIAME
API_USER = "api-pme360@sitiame-capital.com"
LINKED_PARTY_DOCTYPES = ("Customer", "Supplier")


def company_field_definitions():
	return {
		doctype: [
			{
				"fieldname": COMPANY_FIELD,
				"label": "Société",
				"fieldtype": "Link",
				"options": "Company",
				"insert_after": _INSERT_AFTER[doctype],
				"in_standard_filter": 1,
				"no_copy": 1,
				"description": "Société à laquelle appartient cette fiche : seuls ses comptes la voient.",
			}
		]
		for doctype in PARTY_DOCTYPES
	}


_INSERT_AFTER = {
	"Customer": "customer_group",
	"Supplier": "supplier_group",
	"Contact": "company_name",
	"Address": "address_title",
}


def create_company_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(company_field_definitions(), update=True)


def company_of(user):
	"""The PME company of `user` (its Company User Permission), or None."""
	if not user:
		return None
	return frappe.db.get_value("User Permission", {"user": user, "allow": "Company"}, "for_value")


def _linked_party_company(doc):
	for link in doc.get("links") or []:
		if link.get("link_doctype") in LINKED_PARTY_DOCTYPES and link.get("link_name"):
			company = frappe.db.get_value(link.link_doctype, link.link_name, COMPANY_FIELD)
			if company:
				return company
	return None


def default_company(doc, user=None):
	user = user or frappe.session.user
	if doc.doctype == "Contact" and doc.get("user"):
		company = company_of(doc.user)
		if company:
			return company
	if doc.doctype in ("Contact", "Address"):
		company = _linked_party_company(doc)
		if company:
			return company
	company = company_of(user)
	if company:
		return company
	if user == API_USER:
		return None
	if frappe.db.exists("Company", SITIAME_COMPANY):
		return SITIAME_COMPANY
	return None


def _has_field(doctype):
	return frappe.get_meta(doctype).has_field(COMPANY_FIELD)


def set_company(doc, method=None):
	"""before_insert: fills the company when the creator left it empty."""
	if doc.get(COMPANY_FIELD) or not _has_field(doc.doctype):
		return
	company = default_company(doc)
	if company:
		doc.set(COMPANY_FIELD, company)


def attach_user_contacts(doc, method=None):
	"""User Permission after_insert: a PME user's own Contact is created
	with the User, before this permission exists -- it joins the PME's
	company now."""
	if doc.allow != "Company" or not doc.user or not _has_field("Contact"):
		return
	for name in frappe.get_all("Contact", filters={"user": doc.user}, pluck="name"):
		frappe.db.set_value("Contact", name, COMPANY_FIELD, doc.for_value, update_modified=False)


def own_party_filters():
	"""For lookups that bypass permissions (OCR party matching): a PME only
	matches its own parties. Staff lookups are unchanged."""
	company = company_of(frappe.session.user)
	if company and _has_field("Customer"):
		return {COMPANY_FIELD: company}
	return {}


def backfill_plan():
	"""(doctype, name, company) for every record without a company: a PME
	user's own Contact goes to that PME, everything else to SITIAME (all
	existing records were created by staff, PME360 or Administrator and are
	used by SITIAME only -- measured 2026-10-01)."""
	pme_company = {}
	for row in frappe.get_all("User Permission", filters={"allow": "Company"}, fields=["user", "for_value"], order_by="creation asc"):
		pme_company.setdefault(row.user, row.for_value)

	plan = []
	for doctype in PARTY_DOCTYPES:
		fields = ["name", "user"] if doctype == "Contact" else ["name"]
		for row in frappe.get_all(doctype, filters={COMPANY_FIELD: ["is", "not set"]}, fields=fields, order_by="creation asc"):
			plan.append((doctype, row.name, pme_company.get(row.get("user")) or SITIAME_COMPANY))
	return plan


def backfill(dry_run=True):
	plan = backfill_plan()
	if not dry_run:
		for doctype, name, company in plan:
			frappe.db.set_value(doctype, name, COMPANY_FIELD, company, update_modified=False)
	return plan
