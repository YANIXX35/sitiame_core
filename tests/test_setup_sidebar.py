# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""The "Journal des ecritures" entry added to the Payments and Invoicing
sidebars, right after Journal Entry (sitiame_core.setup)."""

import sys
import types

import frappe
import pytest

# setup.py imports frappe's create_custom_fields, absent from the stub
for _name in ("frappe.custom", "frappe.custom.doctype", "frappe.custom.doctype.custom_field", "frappe.custom.doctype.custom_field.custom_field"):
	sys.modules.setdefault(_name, types.ModuleType(_name))
_cf = sys.modules["frappe.custom.doctype.custom_field.custom_field"]
if not hasattr(_cf, "create_custom_fields"):
	_cf.create_custom_fields = lambda *args, **kwargs: None

from sitiame_core import setup  # noqa: E402


@pytest.fixture
def sidebars(monkeypatch):
	state = {
		"items": {
			"Payments": [("Payment Entry", 3), ("Journal Entry", 4), ("Payment Request", 5)],
			"Invoicing": [("Payment Entry", 15), ("Journal Entry", 16), ("Payment Request", 17)],
		},
		"inserted": [],
		"shifted": [],
	}

	def exists(doctype, filters=None):
		if doctype == "Workspace Sidebar":
			return filters in state["items"]
		parent, link_to = filters["parent"], filters["link_to"]
		return any(link == link_to for link, idx in state["items"].get(parent, []))

	def get_value(doctype, filters, field):
		return next((idx for link, idx in state["items"].get(filters["parent"], []) if link == filters["link_to"]), None)

	class Row(dict):
		def db_insert(self):
			state["inserted"].append((self["parent"], self["idx"], self["link_to"], self["label"]))
			state["items"][self["parent"]].append((self["link_to"], self["idx"]))

	monkeypatch.setattr(frappe.db, "exists", exists, raising=False)
	monkeypatch.setattr(frappe.db, "get_value", get_value, raising=False)
	monkeypatch.setattr(frappe.db, "sql", lambda query, params=None: state["shifted"].append(params), raising=False)
	monkeypatch.setattr(frappe.db, "commit", lambda: None, raising=False)
	monkeypatch.setattr(frappe, "clear_cache", lambda: None, raising=False)
	monkeypatch.setattr(frappe, "get_doc", lambda d: Row(d), raising=False)
	return state


def test_added_right_after_journal_entry_in_both_sidebars(sidebars):
	setup.add_journal_to_payment_sidebars()
	assert sidebars["inserted"] == [
		("Payments", 5, "Journal des ecritures", "Journal des écritures"),
		("Invoicing", 17, "Journal des ecritures", "Journal des écritures"),
	]
	assert sidebars["shifted"] == [("Payments", 4), ("Invoicing", 16)]


def test_running_again_adds_nothing(sidebars):
	setup.add_journal_to_payment_sidebars()
	setup.add_journal_to_payment_sidebars()
	assert len(sidebars["inserted"]) == 2


def test_a_missing_sidebar_is_skipped(sidebars):
	del sidebars["items"]["Invoicing"]
	setup.add_journal_to_payment_sidebars()
	assert [row[0] for row in sidebars["inserted"]] == ["Payments"]
