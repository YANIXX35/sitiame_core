# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Each PME account has its own liasse (liasse_scope.py)."""

import frappe
import pytest

from sitiame_core import liasse_scope as ls


@pytest.fixture
def ledger(monkeypatch):
	roles = {"pme@a.ci": ["PME Client", "Accounts Manager"], "compta@sitiame.ci": ["Accounts Manager"]}
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
