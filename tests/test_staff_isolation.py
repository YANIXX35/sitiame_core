# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Staff accounts don't see each other's business documents; PME accounts
and exempt users are untouched."""

import frappe
import pytest

from sitiame_core import staff_isolation as iso

STAFF = ["yanisse@x.com", "elie@x.com", "joseph@x.com"]


@pytest.fixture(autouse=True)
def staff(monkeypatch):
	monkeypatch.setattr(frappe, "local", frappe._dict(), raising=False)
	monkeypatch.setattr(frappe.db, "sql_list", lambda *a, **k: list(STAFF), raising=False)
	monkeypatch.setattr(frappe.db, "escape", lambda value: f"'{value}'", raising=False)


def doc(owner, doctype="Sales Invoice"):
	return frappe._dict(doctype=doctype, owner=owner)


def test_staff_list_hides_other_staff_documents():
	condition = iso.get_permission_query_conditions("yanisse@x.com", doctype="Sales Invoice")
	assert condition == "`tabSales Invoice`.`owner` not in ('elie@x.com', 'joseph@x.com')"


def test_pme_account_gets_no_extra_filter():
	assert iso.get_permission_query_conditions("pme@client.com", doctype="Sales Invoice") == ""


def test_doctype_outside_the_list_is_not_filtered():
	assert iso.get_permission_query_conditions("yanisse@x.com", doctype="Company") == ""


@pytest.mark.parametrize(
	"owner, allowed",
	[
		("yanisse@x.com", True),  # own document
		("elie@x.com", False),  # another staff member
		("api-pme360@sitiame-capital.com", True),  # PME360 sync
		("pme@client.com", True),  # a PME account
	],
)
def test_staff_opening_a_document(owner, allowed):
	assert iso.has_permission(doc(owner), "read", "yanisse@x.com") is allowed


def test_pme_account_opening_any_document_is_left_to_frappe():
	assert iso.has_permission(doc("elie@x.com"), "read", "pme@client.com") is True


def test_has_permission_always_returns_a_boolean_outside_the_list():
	# Frappe reads None as a refusal
	assert iso.has_permission(doc("elie@x.com", "Company"), "read", "yanisse@x.com") is True


def test_staff_query_runs_once_per_request(monkeypatch):
	calls = []
	monkeypatch.setattr(frappe.db, "sql_list", lambda *a, **k: calls.append(1) or list(STAFF))
	iso.get_permission_query_conditions("yanisse@x.com", doctype="Item")
	iso.has_permission(doc("elie@x.com"), "read", "yanisse@x.com")
	assert len(calls) == 1
