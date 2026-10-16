# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Each PME account has its own liasse (liasse_scope.py)."""

import frappe
import pytest

from sitiame_core import liasse_scope as ls


@pytest.fixture
def ledger(monkeypatch):
	roles = {"pme@a.ci": ["PME Client", "Accounts Manager"], "pme2@a.ci": ["PME Client"], "compta@sitiame.ci": ["Accounts Manager"]}
	monkeypatch.setattr(frappe, "get_roles", lambda user=None: roles.get(user, []), raising=False)
	monkeypatch.setattr(frappe.db, "sql_list", lambda q, *a: ["Sales Invoice", "Journal Entry", "Bogus`; drop", None], raising=False)
	monkeypatch.setattr(frappe.db, "exists", lambda doctype, name=None: name in ("Sales Invoice", "Journal Entry"), raising=False)
	monkeypatch.setattr(frappe.db, "escape", lambda v: "'" + v.replace("'", "''") + "'", raising=False)


def test_pme_liasse_keeps_only_its_own_vouchers(ledger):
	condition, params = ls.owner_condition("A", user="pme@a.ci")
	assert params == {"liasse_owner": "pme@a.ci"}
	assert "gle.voucher_type = 'Sales Invoice'" in condition
	assert "select name from `tabSales Invoice` where owner = %(liasse_owner)s" in condition
	assert "Bogus" not in condition  # only real doctypes reach the SQL


@pytest.mark.parametrize("user", ["compta@sitiame.ci", "Administrator"])
def test_staff_see_the_whole_company(ledger, user):
	assert ls.owner_condition("A", user=user) == ("", {})


def test_no_alias_for_single_table_queries(ledger):
	condition, _params = ls.owner_condition("A", alias="", user="pme@a.ci")
	assert "(voucher_type = 'Sales Invoice'" in condition and "gle." not in condition


def test_pme_with_an_empty_ledger_sees_nothing(ledger, monkeypatch):
	monkeypatch.setattr(frappe.db, "sql_list", lambda q, *a: [], raising=False)
	assert ls.owner_condition("A", user="pme@a.ci")[0] == " and 1 = 0"


@pytest.fixture
def company(monkeypatch):
	monkeypatch.setattr(ls, "_company", lambda user: {"pme@a.ci": "A", "pme2@a.ci": "A"}.get(user))


def test_pme_ledger_lines_are_its_own_vouchers(ledger, company):
	condition = ls.get_permission_query_conditions("pme@a.ci", "GL Entry")
	assert condition.startswith("(`tabGL Entry`.company = 'A' and (")
	assert "select name from `tabSales Invoice` where owner = 'pme@a.ci'" in condition


def test_staff_ledger_is_unfiltered(ledger, company):
	assert ls.get_permission_query_conditions("compta@sitiame.ci", "GL Entry") == ""


def test_ledger_line_opens_only_for_its_voucher_owner(ledger, company, monkeypatch):
	monkeypatch.setattr(frappe.db, "get_value", lambda dt, name, field: "pme@a.ci", raising=False)
	line = frappe._dict(company="A", voucher_type="Sales Invoice", voucher_no="FV-1")
	assert ls.has_permission(line, "read", "pme@a.ci") is True
	assert ls.has_permission(line, "read", "pme2@a.ci") is False
	assert ls.has_permission(frappe._dict(line, company="B"), "read", "pme@a.ci") is False


def test_trial_balance_refused_when_the_company_is_shared(ledger, monkeypatch):
	monkeypatch.setattr(frappe, "session", frappe._dict(user="pme@a.ci"), raising=False)
	monkeypatch.setattr(ls, "shares_company", lambda user=None: True)
	with pytest.raises(frappe.PermissionError):
		ls.guard_unscoped_report("Trial Balance")
	ls.guard_unscoped_report("General Ledger")  # filtered by ERPNext itself
	monkeypatch.setattr(ls, "shares_company", lambda user=None: False)
	ls.guard_unscoped_report("Trial Balance")  # alone in its company: same figures


def test_hooked_on_the_ledgers():
	from sitiame_core import hooks

	for doctype in ls.LEDGER_DOCTYPES:
		assert hooks.permission_query_conditions[doctype] == "sitiame_core.liasse_scope.get_permission_query_conditions"
		assert hooks.has_permission[doctype] == "sitiame_core.liasse_scope.has_permission"
	assert "sitiame_core.liasse_scope.patch_unscoped_reports" in hooks.before_request
