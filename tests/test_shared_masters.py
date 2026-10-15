# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Shared lists read-only for a PME (shared_masters.py, audit D7)."""

import frappe
import pytest

from sitiame_core import hooks, shared_masters as sm


@pytest.fixture(autouse=True)
def roles(monkeypatch):
	users = {"pme@client.ci": ["PME Client", "Purchase Master Manager"], "compta@sitiame.ci": ["System Manager"]}
	monkeypatch.setattr(frappe, "get_roles", lambda user=None: users.get(user, []), raising=False)


def doc(doctype):
	return frappe._dict(doctype=doctype, name="Services")


@pytest.mark.parametrize("doctype", sorted(sm.READ_ONLY_FOR_PME))
@pytest.mark.parametrize("ptype, allowed", [("read", True), ("select", True), ("write", False), ("create", False), ("delete", False)])
def test_pme_reads_but_never_changes_a_shared_list(doctype, ptype, allowed):
	assert sm.has_permission(doc(doctype), ptype, "pme@client.ci") is allowed


@pytest.mark.parametrize("ptype, allowed", [("read", True), ("write", True), ("create", True), ("delete", False)])
def test_pme_sets_its_own_account_on_a_payment_mode_but_cannot_delete_it(ptype, allowed):
	assert sm.has_permission(doc("Mode of Payment"), ptype, "pme@client.ci") is allowed


@pytest.mark.parametrize("user", ["compta@sitiame.ci", "Administrator"])
def test_staff_maintain_the_lists(user):
	assert all(sm.has_permission(doc(dt), "delete", user) is True for dt in sm.SHARED_MASTERS)


def test_answers_are_booleans():
	"""Frappe 16 reads any falsy answer, None included, as a refusal."""
	for user in ("pme@client.ci", "compta@sitiame.ci"):
		for dt in sm.SHARED_MASTERS:
			assert isinstance(sm.has_permission(doc(dt), "read", user), bool)


def test_hooked_on_every_shared_list():
	assert all(hooks.has_permission.get(dt) == "sitiame_core.shared_masters.has_permission" for dt in sm.SHARED_MASTERS)
