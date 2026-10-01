# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Month closing (api.get_month_closing_status / close_month): only for a
company the caller may read (audit 2026-10-01: another PME's month was
readable)."""

import datetime

import frappe
import pytest

from sitiame_core import api


class Refused(Exception):
	pass


@pytest.fixture
def world(monkeypatch):
	state = {"readable": {"OOO"}, "queried": [], "inserted": []}

	def throw(message, exc=None):
		raise Refused(message)

	def has_permission(doctype, ptype="read", doc=None, throw=False, **kwargs):
		state["checked"] = (doctype, ptype, doc)
		ok = doc in state["readable"]
		if not ok and throw:
			raise Refused("no access")
		return ok

	def sql(query, values=None, *a, **k):
		state["queried"].append(values["company"])
		return [[3]]

	class Doc(frappe._dict):
		def insert(self):
			state["inserted"].append(self.get("doctype"))
			self.name = "X"

	monkeypatch.setattr(frappe, "throw", throw, raising=False)
	monkeypatch.setattr(frappe, "has_permission", has_permission, raising=False)
	monkeypatch.setattr(frappe.db, "sql", sql, raising=False)
	monkeypatch.setattr(frappe.db, "count", lambda *a, **k: 1, raising=False)
	monkeypatch.setattr(frappe.db, "exists", lambda *a, **k: False, raising=False)
	monkeypatch.setattr(frappe.db, "get_value", lambda *a, **k: None, raising=False)
	monkeypatch.setattr(frappe.db, "commit", lambda: None, raising=False)
	monkeypatch.setattr(frappe, "get_doc", lambda d: Doc(d), raising=False)
	monkeypatch.setattr(frappe, "get_hooks", lambda name: [], raising=False)
	monkeypatch.setattr(frappe.utils, "get_last_day", lambda d: datetime.date(2026, 9, 30), raising=False)
	return state


def test_own_company_status_is_read(world):
	result = api.get_month_closing_status("OOO", "2026-09")
	assert result["entries_count"] == 3 and world["queried"] == ["OOO"]
	assert world["checked"] == ("Company", "read", "OOO")


def test_another_company_status_is_refused_before_any_query(world):
	with pytest.raises(Refused):
		api.get_month_closing_status("SITIAME", "2026-09")
	assert world["queried"] == []


def test_another_company_cannot_be_closed(world):
	with pytest.raises(Refused):
		api.close_month("SITIAME", "2026-09")
	assert world["inserted"] == []


def test_own_company_month_is_closed(world):
	api.close_month("OOO", "2026-09", notes="ok")
	assert world["inserted"] == ["ERP Month Closure", "Accounting Period"]


def test_missing_company_is_refused(world):
	with pytest.raises(Refused):
		api.get_month_closing_status("", "2026-09")
