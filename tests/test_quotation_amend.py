# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""'Modifier le devis' (quotation.amend_quotation): a validated quotation is
cancelled and amended into a new draft, never edited in place."""

import frappe
import pytest

from sitiame_core import quotation


class Refused(Exception):
	pass


def _throw(message, exc=None):
	raise Refused(message)


class Quotation(frappe._dict):
	def __init__(self, log, **fields):
		super().__init__(doctype="Quotation", **fields)
		self.__dict__["log"] = log

	def check_permission(self, ptype):
		self.log.append(("check", ptype))
		if ptype in self.log_denied():
			raise frappe.PermissionError(ptype)

	def log_denied(self):
		return self.get("denied") or ()

	def cancel(self):
		self.log.append(("cancel", self.name))
		self.docstatus = 2

	def insert(self):
		self.log.append(("insert", self.amended_from, self.docstatus))
		self.name = f"{self.amended_from}-1"
		return self


@pytest.fixture
def world(monkeypatch):
	state = {"log": [], "doc": None, "can_create": True}
	monkeypatch.setattr(frappe, "throw", _throw, raising=False)
	monkeypatch.setattr(frappe, "get_doc", lambda doctype, name: state["doc"], raising=False)
	monkeypatch.setattr(frappe, "has_permission", lambda doctype, ptype=None, *a, **k: state["can_create"], raising=False)
	monkeypatch.setattr(frappe, "copy_doc", lambda doc: Quotation(state["log"], **{k: v for k, v in doc.items() if k not in ("name", "doctype")}), raising=False)
	state["new"] = lambda **f: Quotation(state["log"], name="SAL-QTN-2026-00002", company="binks", **f)
	return state


def test_validated_quotation_becomes_a_new_draft(world):
	world["doc"] = world["new"](docstatus=1, status="Open")
	assert quotation.amend_quotation("SAL-QTN-2026-00002") == "SAL-QTN-2026-00002-1"
	assert world["log"] == [("check", "cancel"), ("cancel", "SAL-QTN-2026-00002"), ("insert", "SAL-QTN-2026-00002", 0)]


@pytest.mark.parametrize("docstatus, match", [(0, "brouillon"), (2, "annulé")])
def test_draft_or_cancelled_quotation_is_not_amended(world, docstatus, match):
	world["doc"] = world["new"](docstatus=docstatus, status="Draft")
	with pytest.raises(Refused, match=match):
		quotation.amend_quotation("SAL-QTN-2026-00002")
	assert world["log"] == []


@pytest.mark.parametrize("status", ["Ordered", "Partially Ordered"])
def test_ordered_quotation_is_changed_on_the_order(world, status):
	world["doc"] = world["new"](docstatus=1, status=status)
	with pytest.raises(Refused, match="commande"):
		quotation.amend_quotation("SAL-QTN-2026-00002")
	assert ("cancel", "SAL-QTN-2026-00002") not in world["log"]


def test_no_cancel_right_no_change(world):
	"""Another company's quotation, or a user without the cancel right:
	the permission check (with the isolation hooks) refuses before anything."""
	world["doc"] = world["new"](docstatus=1, status="Open", denied=("cancel",))
	with pytest.raises(frappe.PermissionError):
		quotation.amend_quotation("SAL-QTN-2026-00002")
	assert world["log"] == [("check", "cancel")]


def test_no_create_right_no_change(world):
	world["doc"] = world["new"](docstatus=1, status="Open")
	world["can_create"] = False
	with pytest.raises(Refused, match="créer un devis"):
		quotation.amend_quotation("SAL-QTN-2026-00002")
	assert ("cancel", "SAL-QTN-2026-00002") not in world["log"]
