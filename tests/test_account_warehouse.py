# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""One warehouse per PME account (account_warehouse.py)."""

import frappe
import pytest

from sitiame_core import account_warehouse as aw, hooks


@pytest.fixture
def accounts(monkeypatch):
	mapping = {"a@sys.ci": "Magasins - SYS", "b@sys.ci": "Magasin B - SYS"}
	monkeypatch.setattr(frappe, "session", frappe._dict(user="b@sys.ci"), raising=False)
	monkeypatch.setattr(aw, "account_warehouse", lambda user=None: mapping.get(user or frappe.session.user))
	monkeypatch.setattr(aw, "_others", lambda company, user: {w for u, w in mapping.items() if u != user})
	monkeypatch.setattr(frappe, "get_cached_value", lambda doctype, name, field: name != "Service", raising=False)
	return mapping


def _doc(doctype, **values):
	doc = frappe._dict(doctype=doctype, company="SYS", **values)
	doc.set = lambda field, value: doc.__setitem__(field, value)
	return doc


def test_an_empty_warehouse_becomes_the_account_s(accounts):
	rows = [frappe._dict(item_code="Riz"), frappe._dict(item_code="Service")]
	doc = _doc("Delivery Note", items=rows)
	aw.set_account_warehouse(doc)
	assert doc.set_warehouse == "Magasin B - SYS"
	assert rows[0].warehouse == "Magasin B - SYS"
	assert not rows[1].get("warehouse")  # a service holds no stock


def test_another_account_s_warehouse_is_refused(accounts):
	doc = _doc("Delivery Note", set_warehouse="Magasins - SYS", items=[frappe._dict(item_code="Riz", warehouse="Magasins - SYS")])
	with pytest.raises(frappe.PermissionError):
		aw.set_account_warehouse(doc)


def test_stock_entry_receipt_goes_into_the_account_s_warehouse(accounts):
	row = frappe._dict(item_code="Riz", set=None)
	row.set = lambda field, value: row.__setitem__(field, value)
	doc = _doc("Stock Entry", purpose="Material Receipt", items=[row])
	aw.set_account_warehouse(doc)
	assert doc.to_warehouse == row.t_warehouse == "Magasin B - SYS"


def test_staff_documents_are_untouched(accounts, monkeypatch):
	monkeypatch.setattr(frappe, "session", frappe._dict(user="compta@sitiame.ci"), raising=False)
	doc = _doc("Delivery Note", items=[frappe._dict(item_code="Riz")])
	aw.set_account_warehouse(doc)
	assert not doc.get("set_warehouse")


def test_stock_reports_read_the_account_s_warehouse_only(accounts):
	assert aw._narrow({"company": "SYS", "warehouse": ["Magasins - SYS"]}, True).warehouse == ["Magasin B - SYS"]
	assert aw._narrow({"company": "SYS"}, False).warehouse == "Magasin B - SYS"


def test_hooked_on_every_stock_document():
	for doctype in aw.STOCK_DOCTYPES:
		assert "sitiame_core.account_warehouse.set_account_warehouse" in hooks.doc_events[doctype]["before_validate"]
	assert "sitiame_core.account_warehouse.patch_stock_reports" in hooks.before_request
	assert "/assets/sitiame_core/js/account_warehouse.js" in hooks.app_include_js
