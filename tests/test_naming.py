# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Document numbers continuous per company and per fiscal year (naming.py):
ERPNext's shared series gave a PME the holes of the others' invoices."""

import datetime

import frappe
import pytest

from sitiame_core import naming

FY2026 = (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31), "2026")


def test_rule_spec_for_a_sales_invoice():
	spec = naming.rule_spec("Sales Invoice", "SYS-TECHNOLOGIES SARL", "SYSTE", FY2026)
	assert spec["prefix"] == "FV-SYSTE-2026-" and spec["prefix_digits"] == 5
	assert spec["conditions"] == [
		{"field": "company", "condition": "=", "value": "SYS-TECHNOLOGIES SARL"},
		{"field": "posting_date", "condition": ">=", "value": "2026-01-01"},
		{"field": "posting_date", "condition": "<=", "value": "2026-12-31"},
	]


def test_order_documents_use_their_transaction_date():
	spec = naming.rule_spec("Quotation", "C", "C", FY2026)
	assert spec["prefix"] == "DEV-C-2026-" and {c["field"] for c in spec["conditions"][1:]} == {"transaction_date"}


@pytest.mark.parametrize("name, label", [("2026", "2026"), ("2025-2026", "2025"), ("2025/26", "2025")])
def test_year_label_never_puts_a_separator_in_names(name, label):
	assert naming._year_label(name, datetime.date(int(label), 1, 1)) == label


@pytest.fixture
def site(monkeypatch):
	state = {"rules": {}, "inserted": []}

	class Rule(frappe._dict):
		def insert(self, ignore_permissions=False):
			state["rules"][(self.document_type, self.prefix)] = self
			state["inserted"].append(self.prefix)
			return self

	def exists(doctype, filters=None):
		if doctype == "DocType":
			return True
		return (filters["document_type"], filters["prefix"]) in state["rules"]

	monkeypatch.setattr(frappe.db, "exists", exists, raising=False)
	monkeypatch.setattr(frappe.db, "get_value", lambda doctype, name, field=None, **k: {"A SARL": "AS", "B SARL": "BS"}.get(name), raising=False)
	def get_all(doctype, **k):
		if doctype == "Fiscal Year":
			return [frappe._dict(name="2026", year_start_date=FY2026[0], year_end_date=FY2026[1])]
		return ["A SARL", "B SARL"]

	monkeypatch.setattr(frappe, "get_all", get_all, raising=False)
	monkeypatch.setattr(frappe, "get_doc", lambda spec: Rule(spec), raising=False)
	return state


def test_every_company_gets_its_own_rules_once(site):
	assert naming.ensure_rules(fiscal_years=[FY2026]) == 2 * len(naming.NUMBERED_DOCTYPES)
	assert "FV-AS-2026-" in site["inserted"] and "FV-BS-2026-" in site["inserted"]
	assert naming.ensure_rules(fiscal_years=[FY2026]) == 0  # idempotent


def test_new_company_and_new_fiscal_year(site):
	company = frappe._dict(name="A SARL", flags=frappe._dict(in_insert=True))
	naming.on_company_update(company)
	assert all(p.startswith(tuple(f"{x}-AS-" for x, _ in naming.NUMBERED_DOCTYPES.values())) for p in site["inserted"])
	site["inserted"].clear()
	naming.on_company_update(frappe._dict(name="A SARL", flags=frappe._dict(in_insert=False)))  # later save
	assert site["inserted"] == []
