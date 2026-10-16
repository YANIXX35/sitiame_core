# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Customers, suppliers, contacts and addresses carry a company so the PME's
Company User Permission confines them (sitiame_core.party_isolation)."""

import frappe
import pytest

from sitiame_core import ocr_invoice
from sitiame_core import party_isolation as pi

PME_USERS = {"pme-a@x.com": "A SARL", "pme-b@x.com": "B SARL"}
PARTY_COMPANY = {("Customer", "CLIENT-A"): "A SARL", ("Supplier", "FOURN-B"): "B SARL"}


class Doc(frappe._dict):
	def set(self, key, value):
		self[key] = value


@pytest.fixture(autouse=True)
def world(monkeypatch):
	state = {"set": [], "user": "Administrator", "companies": {"SITIAME", "A SARL", "B SARL"}, "has_field": True, "lookups": [], "errors": []}

	def get_value(doctype, filters=None, fieldname=None, *a, **k):
		if doctype == "User Permission":
			return PME_USERS.get(filters["user"])
		if fieldname == pi.COMPANY_FIELD:
			return PARTY_COMPANY.get((doctype, filters))
		state["lookups"].append((doctype, dict(filters) if isinstance(filters, dict) else filters))
		return None

	def get_all(doctype, filters=None, fields=None, pluck=None, order_by=None, **k):
		if doctype == "User Permission":
			user = (filters or {}).get("user")
			val = PME_USERS.get(user)
			return [val] if val else []
		return []

	monkeypatch.setattr(frappe.db, "get_value", get_value, raising=False)
	monkeypatch.setattr(frappe.db, "exists", lambda doctype, name=None: name in state["companies"], raising=False)
	monkeypatch.setattr(
		frappe.db, "set_value", lambda dt, name, field, value, **k: state["set"].append((dt, name, value)), raising=False
	)
	monkeypatch.setattr(frappe.db, "commit", lambda: None, raising=False)
	monkeypatch.setattr(frappe, "session", frappe._dict(user="Administrator"), raising=False)
	monkeypatch.setattr(
		frappe, "get_meta", lambda doctype: frappe._dict(has_field=lambda f: state["has_field"]), raising=False
	)
	monkeypatch.setattr(
		frappe, "log_error", lambda title="", message="", **k: state["errors"].append(title), raising=False
	)
	# get_all is used by company_of and backfill_plan
	_orig_get_all = getattr(frappe, "get_all", None)
	def _get_all(doctype, filters=None, fields=None, pluck=None, order_by=None, **k):
		if doctype == "User Permission":
			user = (filters or {}).get("user")
			val = PME_USERS.get(user)
			return [val] if val else []
		if _orig_get_all:
			return _orig_get_all(doctype, filters=filters, fields=fields, pluck=pluck, order_by=order_by, **k)
		return []
	monkeypatch.setattr(frappe, "get_all", _get_all, raising=False)
	return state


def as_user(monkeypatch, user):
	monkeypatch.setattr(frappe, "session", frappe._dict(user=user), raising=False)


def new(doctype, **values):
	return Doc(doctype=doctype, **values)


# -- company given at creation --


def test_pme_records_get_the_pme_company(monkeypatch):
	as_user(monkeypatch, "pme-a@x.com")
	for doctype in pi.PARTY_DOCTYPES:
		doc = new(doctype)
		pi.set_company(doc)
		assert doc.company == "A SARL", doctype


def test_an_explicit_company_is_kept(monkeypatch):
	"""PME360 sends company for a PME's customer (findOrCreateCustomerForPme)."""
	as_user(monkeypatch, pi.API_USER)
	doc = new("Customer", company="B SARL")
	pi.set_company(doc)
	assert doc.company == "B SARL"


def test_staff_records_go_to_sitiame(monkeypatch):
	for user in ("Administrator", "comptable@sitiame-capital.com", "Guest"):
		as_user(monkeypatch, user)
		doc = new("Supplier")
		pi.set_company(doc)
		assert doc.company == "SITIAME", user


def test_pme360_api_records_without_company_are_left_empty(monkeypatch):
	"""Not SITIAME: the API creates them for a PME (sport members)."""
	as_user(monkeypatch, pi.API_USER)
	doc = new("Customer")
	pi.set_company(doc)
	assert doc.get("company") is None


def test_a_contact_follows_its_party_then_its_user(monkeypatch):
	as_user(monkeypatch, "Administrator")
	contact = new("Contact", links=[frappe._dict(link_doctype="Customer", link_name="CLIENT-A")])
	pi.set_company(contact)
	assert contact.company == "A SARL"

	address = new("Address", links=[frappe._dict(link_doctype="Supplier", link_name="FOURN-B")])
	pi.set_company(address)
	assert address.company == "B SARL"

	own = new("Contact", user="pme-b@x.com")
	pi.set_company(own)
	assert own.company == "B SARL"


def test_nothing_happens_before_the_field_exists(monkeypatch, world):
	world["has_field"] = False
	as_user(monkeypatch, "pme-a@x.com")
	doc = new("Customer")
	pi.set_company(doc)
	assert doc.get("company") is None


def test_no_sitiame_company_no_default(monkeypatch, world):
	world["companies"] = set()
	doc = new("Customer")
	pi.set_company(doc)
	assert doc.get("company") is None


# -- PME user's own contact --


def test_pme_user_contact_joins_its_company(monkeypatch, world):
	monkeypatch.setattr(frappe, "get_all", lambda doctype, filters=None, pluck=None, **k: ["Contact-A"] if doctype == "Contact" else [], raising=False)
	pi.attach_user_contacts(frappe._dict(allow="Company", user="pme-a@x.com", for_value="A SARL"))
	pi.attach_user_contacts(frappe._dict(allow="Warehouse", user="pme-a@x.com", for_value="WH"))
	assert world["set"] == [("Contact", "Contact-A", "A SARL")]


def test_attach_user_contacts_ignores_empty_for_value(monkeypatch, world):
	"""Bug fix: a User Permission with allow=Company but for_value='' must not
	null-out the Contacts -- that would hide them from their own user."""
	monkeypatch.setattr(frappe, "get_all", lambda doctype, filters=None, pluck=None, **k: ["Contact-A"] if doctype == "Contact" else [], raising=False)
	pi.attach_user_contacts(frappe._dict(allow="Company", user="pme-a@x.com", for_value=""))
	assert world["set"] == [], "empty for_value must not propagate"


def test_protect_company_restores_reassignment():
	"""Bug fix: a PME must not be able to move a record to another tenant by
	editing the company field.  protect_company silently restores the original."""
	doc = Doc(doctype="Customer", name="CLIENT-A", company="B SARL")  # tries to move to B SARL
	pi.protect_company(doc)
	assert doc.company == "A SARL", "company must be restored to original"


def test_protect_company_leaves_new_records_alone():
	"""A new insert has no DB row yet: get_value returns None, nothing to restore."""
	doc = Doc(doctype="Customer", name="NEW-CUS", company="B SARL")
	pi.protect_company(doc)
	assert doc.company == "B SARL", "new record: company must not be touched"


# -- OCR party matching --


def _ocr_get_all(world):
	"""get_all mock for OCR tests: handles User Permission (company_of) and
	records party lookups for assertions."""
	def _impl(doctype, filters=None, **k):
		if doctype == "User Permission":
			user = (filters or {}).get("user")
			val = PME_USERS.get(user)
			return [val] if val else []
		world["lookups"].append((doctype, dict(filters or {})))
		return []
	return _impl


def test_ocr_party_lookup_is_confined_for_a_pme(monkeypatch, world):
	monkeypatch.setattr(frappe, "get_all", _ocr_get_all(world), raising=False)
	as_user(monkeypatch, "pme-a@x.com")
	ocr_invoice._find_party("Supplier", "NSIA")
	assert all(filters.get("company") == "A SARL" for doctype, filters in world["lookups"])
	assert len(world["lookups"]) == 2


def test_ocr_party_lookup_is_unchanged_for_staff(monkeypatch, world):
	"""Non-regression: staff still match any existing party."""
	monkeypatch.setattr(frappe, "get_all", _ocr_get_all(world), raising=False)
	for user in ("Administrator", pi.API_USER, "analyste@sitiame-capital.com"):
		world["lookups"].clear()
		as_user(monkeypatch, user)
		ocr_invoice._find_party("Supplier", "NSIA")
		assert all("company" not in filters for doctype, filters in world["lookups"]), user


# -- backfill --


def test_backfill_plan(monkeypatch):
	rows = {
		"User Permission": [frappe._dict(user="pme-a@x.com", for_value="A SARL")],
		"Customer": [frappe._dict(name="QA-TEST")],
		"Supplier": [frappe._dict(name="NSIA")],
		"Contact": [frappe._dict(name="Contact-A", user="pme-a@x.com"), frappe._dict(name="joseph", user="joseph@sitiame-capital.com"), frappe._dict(name="ABC-NSIA", user=None)],
		"Address": [frappe._dict(name="NSIA-Facturation")],
	}

	def get_all(doctype, filters=None, fields=None, **k):
		if doctype != "User Permission":
			assert filters == {"company": ["is", "not set"]}
		return rows[doctype]

	monkeypatch.setattr(frappe, "get_all", get_all, raising=False)
	assert pi.backfill_plan() == [
		("Customer", "QA-TEST", "SITIAME"),
		("Supplier", "NSIA", "SITIAME"),
		("Contact", "Contact-A", "A SARL"),
		("Contact", "joseph", "SITIAME"),
		("Contact", "ABC-NSIA", "SITIAME"),
		("Address", "NSIA-Facturation", "SITIAME"),
	]


def test_backfill_dry_run_writes_nothing(monkeypatch, world):
	monkeypatch.setattr(pi, "backfill_plan", lambda: [("Customer", "QA-TEST", "SITIAME")])
	assert pi.backfill(dry_run=True) == [("Customer", "QA-TEST", "SITIAME")]
	assert world["set"] == []
	pi.backfill(dry_run=False)
	assert world["set"] == [("Customer", "QA-TEST", "SITIAME")]


def test_items_are_not_confined():
	"""PME360 shares one Item between PMEs: left out on purpose."""
	assert "Item" not in pi.PARTY_DOCTYPES


def test_hooks_wire_every_party_doctype():
	from sitiame_core import hooks

	for doctype in pi.PARTY_DOCTYPES:
		assert hooks.doc_events[doctype]["before_insert"] == "sitiame_core.party_isolation.set_company"
		assert hooks.doc_events[doctype]["before_save"] == "sitiame_core.party_isolation.protect_company"
	after = hooks.doc_events["User Permission"]["after_insert"]
	assert after[:2] == ["sitiame_core.portfolio.assign_pending_pme", "sitiame_core.party_isolation.attach_user_contacts"]
