# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Customers and suppliers are private to the PME account that created them,
even from the other accounts of the same company (asked 2026-10-15); Sitiame
staff still see them all. A name already taken gets " - N"."""

import types

import frappe
import pytest

from sitiame_core import party_isolation as pi
from sitiame_core import staff_isolation as iso

COMPANIES = {"ekonan@sys.ci": "SYS", "badiko@sys.ci": "SYS", "pme@other.ci": "OTHER"}
STAFF = ["compta@sitiame.ci"]


@pytest.fixture(autouse=True)
def world(monkeypatch):
	monkeypatch.setattr(frappe, "local", types.SimpleNamespace(), raising=False)
	monkeypatch.setattr(frappe.db, "sql_list", lambda *a, **k: list(STAFF), raising=False)
	monkeypatch.setattr(frappe.db, "escape", lambda value: f"'{value}'", raising=False)
	monkeypatch.setattr(frappe, "get_roles", lambda user=None: ["PME Client"] if user in COMPANIES else ["Accounts Manager"], raising=False)
	monkeypatch.setattr(pi, "company_of", lambda user: COMPANIES.get(user))


def party(doctype, owner, company="SYS"):
	return frappe._dict(doctype=doctype, owner=owner, company=company)


@pytest.mark.parametrize("doctype", ["Supplier", "Customer"])
def test_pme_list_shows_only_its_own_parties(doctype):
	condition = iso.get_permission_query_conditions("badiko@sys.ci", doctype=doctype)
	assert condition == f"`tab{doctype}`.`company` = 'SYS' and `tab{doctype}`.`owner` = 'badiko@sys.ci'"


def test_company_documents_stay_shared_inside_the_company():
	"""Invoices, quotations... are still shared by the company's accounts."""
	assert iso.get_permission_query_conditions("badiko@sys.ci", doctype="Purchase Invoice") == "`tabPurchase Invoice`.`company` = 'SYS'"


@pytest.mark.parametrize(
	"user, owner, company, allowed",
	[
		("ekonan@sys.ci", "ekonan@sys.ci", "SYS", True),  # its own supplier
		("badiko@sys.ci", "ekonan@sys.ci", "SYS", False),  # a colleague's, same company
		("pme@other.ci", "ekonan@sys.ci", "SYS", False),  # another PME's
		("compta@sitiame.ci", "ekonan@sys.ci", "SYS", True),  # Sitiame staff
	],
)
@pytest.mark.parametrize("doctype", ["Supplier", "Customer"])
def test_opening_a_party(doctype, user, owner, company, allowed):
	assert iso.has_permission(party(doctype, owner, company), "read", user) is allowed


def test_colleague_invoice_still_opens():
	invoice = frappe._dict(doctype="Purchase Invoice", owner="ekonan@sys.ci", company="SYS")
	assert iso.has_permission(invoice, "read", "badiko@sys.ci") is True


def test_scanned_invoice_only_matches_the_account_s_own_parties(monkeypatch):
	monkeypatch.setattr(frappe, "session", frappe._dict(user="badiko@sys.ci"), raising=False)
	monkeypatch.setattr(frappe, "get_meta", lambda doctype: frappe._dict(has_field=lambda f: True), raising=False)
	assert pi.own_party_filters("Supplier") == {"company": "SYS", "owner": "badiko@sys.ci"}
	assert pi.own_party_filters("Contact") == {"company": "SYS"}
	monkeypatch.setattr(frappe, "session", frappe._dict(user="compta@sitiame.ci"), raising=False)
	assert pi.own_party_filters("Supplier") == {}


def test_a_taken_name_gets_a_suffix(monkeypatch):
	taken = {"CIE", "CIE - 1"}
	monkeypatch.setattr(frappe.db, "exists", lambda doctype, name=None: name in taken, raising=False)
	monkeypatch.setattr(frappe, "flags", frappe._dict(), raising=False)
	assert pi.unique_party_name("Supplier", "SODECI") == "SODECI"
	assert pi.unique_party_name("Supplier", "CIE") == "CIE - 2"
