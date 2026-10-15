# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Account setup steps of a PME (onboarding.py)."""

import frappe
import pytest

from sitiame_core import hooks, onboarding as ob


def test_steps_follow_the_setup_order():
	assert [key for key, _label in ob.STEPS] == ["produits", "stocks", "creances", "dettes", "tresorerie"]
	assert ob.SKIPPABLE == {"stocks", "creances", "dettes", "tresorerie"}


@pytest.mark.parametrize("user, roles", [("Administrator", ["PME Client"]), ("compta@sitiame.ci", ["Accounts Manager"])])
def test_staff_and_administrator_never_see_it(monkeypatch, user, roles):
	monkeypatch.setattr(frappe, "session", frappe._dict(user=user), raising=False)
	monkeypatch.setattr(frappe, "get_roles", lambda user=None: roles, raising=False)
	assert ob.get_status() == {"show": False}


def test_products_cannot_be_declared_empty():
	with pytest.raises(Exception):
		ob.skip_step("produits")


def test_staff_cannot_post_openings(monkeypatch):
	monkeypatch.setattr(frappe, "session", frappe._dict(user="compta@sitiame.ci"), raising=False)
	monkeypatch.setattr(frappe, "get_roles", lambda user=None: ["Accounts Manager"], raising=False)
	with pytest.raises(frappe.PermissionError):
		ob.save_cash({"caisse": 1000})


def test_item_code_never_takes_another_pme_item(monkeypatch):
	existing = {"Riz", "Riz - ABC"}
	monkeypatch.setattr(frappe.db, "exists", lambda doctype, name: name in existing, raising=False)
	monkeypatch.setattr(frappe, "get_cached_value", lambda *a, **k: "ABC", raising=False)
	assert ob._item_code("Savon", "X") == "Savon"
	assert ob._item_code("Riz", "X") == "Riz - ABC 2"


def test_desk_script_is_loaded():
	assert "/assets/sitiame_core/js/onboarding.js" in hooks.app_include_js


def test_preview_shows_a_demo_to_a_staff_account(monkeypatch):
	monkeypatch.setattr(frappe, "session", frappe._dict(user="yanisse@sitiame.ci"), raising=False)
	monkeypatch.setattr(frappe, "get_roles", lambda user=None: ["System Manager"], raising=False)
	monkeypatch.setattr(frappe, "defaults", frappe._dict(get_user_default=lambda key: "1"), raising=False)
	status = ob.get_status()
	assert status["show"] and status["preview"]
	assert [s["state"] for s in status["steps"]] == ["todo"] * 5
