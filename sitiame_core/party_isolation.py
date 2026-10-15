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
	"""The PME company of `user` (its Company User Permission), or None.

	Excludes empty for_value rows (a malformed permission that would otherwise
	propagate NULL into every document the user saves).  Logs a warning when
	the user has more than one Company permission -- first created wins, but
	the anomaly should be investigated.
	"""
	if not user:
		return None
	rows = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "Company", "for_value": ["!=", ""]},
		pluck="for_value",
		order_by="creation asc",
	)
	if not rows:
		return None
	if len(rows) > 1:
		frappe.log_error(
			title="party_isolation: multiple Company permissions",
			message=f"User {user!r} has {len(rows)} Company User Permissions: {rows}. First used.",
		)
	return rows[0]


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


def protect_company(doc, method=None):
	"""before_save: silently restores the company field if a PME tries to
	re-assign an existing record to another tenant.  The field is set once on
	creation (set_company / before_insert) and must never change after that.
	On a new insert frappe.db.get_value returns None, so nothing happens.
	"""
	if not _has_field(doc.doctype):
		return
	original = frappe.db.get_value(doc.doctype, doc.name, COMPANY_FIELD)
	if original and doc.get(COMPANY_FIELD) != original:
		doc.set(COMPANY_FIELD, original)


def attach_user_contacts(doc, method=None):
	"""User Permission after_insert: a PME user's own Contact is created
	with the User, before this permission exists -- it joins the PME's
	company now."""
	if doc.allow != "Company" or not doc.user or not doc.for_value or not _has_field("Contact"):
		return
	for name in frappe.get_all("Contact", filters={"user": doc.user}, pluck="name"):
		frappe.db.set_value("Contact", name, COMPANY_FIELD, doc.for_value, update_modified=False)


def unique_party_name(doctype, name):
	"""`name`, or `name - N` when taken: parties are private (to a company,
	to an account), so the one already holding the name is invisible to the
	creator -- a second "CIE" failed with "Duplicate entry" (2026-10-15).
	ERPNext already does this for customers (Customer.get_customer_name)."""
	if not frappe.db.exists(doctype, name) or frappe.flags.in_import:
		return name
	number = 1
	while frappe.db.exists(doctype, f"{name} - {number}"):
		number += 1
	return f"{name} - {number}"


def own_party_filters(doctype=None):
	"""For lookups that bypass permissions (OCR party matching): a PME only
	matches its own parties. Staff lookups are unchanged.

	Pass `doctype` so the check uses the actual target doctype instead of
	always probing Customer -- a partial migration (Customer field present,
	Supplier not yet) would otherwise inject a filter on a missing column.
	"""
	from sitiame_core.staff_isolation import OWNER_ONLY_DOCTYPES

	company = company_of(frappe.session.user)
	check_doctype = doctype or "Customer"
	if company and _has_field(check_doctype):
		filters = {COMPANY_FIELD: company}
		# customers and suppliers are private to the account that created
		# them (staff_isolation.OWNER_ONLY_DOCTYPES)
		if check_doctype in OWNER_ONLY_DOCTYPES and "PME Client" in frappe.get_roles(frappe.session.user):
			filters["owner"] = frappe.session.user
		return filters
	return {}


def backfill_plan():
	"""(doctype, name, company) for every record without a company: a PME
	user's own Contact goes to that PME, everything else to SITIAME (all
	existing records were created by staff, PME360 or Administrator and are
	used by SITIAME only -- measured 2026-10-01)."""
	pme_company = {}
	for row in frappe.get_all("User Permission", filters={"allow": "Company"}, fields=["user", "for_value"], order_by="creation asc"):
		if row.user in pme_company:
			frappe.log_error(
				title="party_isolation backfill: duplicate Company permission",
				message=f"User {row.user!r} already mapped to {pme_company[row.user]!r}; skipping {row.for_value!r}.",
			)
		else:
			pme_company[row.user] = row.for_value

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
		frappe.db.commit()
	return plan
