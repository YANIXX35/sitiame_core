# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Chargé d'affaires (sitiame_core/portfolio.py): portfolio-only access,
four eyes, APIs narrowed to the portfolio."""

import json
import pathlib

import frappe
import pytest

from sitiame_core import portfolio, subscription_api
from sitiame_core.roles import CHARGE_AFFAIRES_ROLE
from sitiame_core.staff_isolation import ISOLATED_DOCTYPES

CA = "ca@sitiame-capital.com"
APP = pathlib.Path(__file__).resolve().parents[1] / "sitiame_core"


class Refused(Exception):
	pass


def _throw(message, exc=None):
	raise Refused(message)


class Doc(frappe._dict):
	def is_new(self):
		return bool(self.get("__new"))


@pytest.fixture
def world(monkeypatch):
	state = {"roles": {CA: [CHARGE_AFFAIRES_ROLE, "All"], "admin@x": ["System Manager"], "analyst@x": [CHARGE_AFFAIRES_ROLE, "Analyste Credit Sitiame"]},
		"portfolio": {CA: ["PME A", "PME B"]}, "user": CA}

	monkeypatch.setattr(frappe, "get_roles", lambda user=None: state["roles"].get(user or state["user"], []), raising=False)
	monkeypatch.setattr(frappe, "session", frappe._dict(user=CA), raising=False)
	monkeypatch.setattr(frappe, "local", frappe._dict(), raising=False)
	monkeypatch.setattr(
		frappe, "get_all",
		lambda doctype, filters=None, pluck=None, **kw: list(state["portfolio"].get(filters[portfolio.PORTFOLIO_FIELD], [])),
		raising=False,
	)
	monkeypatch.setattr(frappe.db, "escape", lambda value: "'" + str(value).replace("'", "\\'") + "'", raising=False)
	monkeypatch.setattr(frappe, "throw", _throw, raising=False)
	return state


# -- who is narrowed --


def test_validators_are_never_narrowed(world):
	assert portfolio.is_charge_affaires(CA)
	assert not portfolio.is_charge_affaires("admin@x")
	assert not portfolio.is_charge_affaires("analyst@x")  # also a validator: sees everything
	for doctype in portfolio.PORTFOLIO_DOCTYPES:
		assert portfolio.get_permission_query_conditions("admin@x", doctype) == ""


def test_company_list_is_the_portfolio(world):
	assert portfolio.get_permission_query_conditions(CA, "Company") == "`tabCompany`.`name` in ('PME A', 'PME B')"
	assert portfolio.get_permission_query_conditions(CA, "Credit Scoring Dossier") == "`tabCredit Scoring Dossier`.`company` in ('PME A', 'PME B')"


def test_empty_portfolio_sees_nothing(world):
	world["portfolio"] = {}
	assert portfolio.get_permission_query_conditions(CA, "Financing Dossier") == "1=0"


def test_own_leads_and_opportunities_only(world):
	assert portfolio.get_permission_query_conditions(CA, "Lead") == (
		"(`tabLead`.`owner` = 'ca@sitiame-capital.com' or `tabLead`.`lead_owner` = 'ca@sitiame-capital.com')"
	)


def test_other_doctypes_are_left_alone(world):
	assert portfolio.get_permission_query_conditions(CA, "Sales Invoice") == ""


def test_single_documents(world):
	assert portfolio.has_permission(Doc(doctype="Company", name="PME A"), user=CA) is True
	assert portfolio.has_permission(Doc(doctype="Company", name="PME Z"), user=CA) is False
	assert portfolio.has_permission(Doc(doctype="Financing Dossier", company="PME Z"), user=CA) is False
	assert portfolio.has_permission(Doc(doctype="Credit Scoring Dossier", company=None), user=CA) is True  # being created
	assert portfolio.has_permission(Doc(doctype="Lead", owner="other@x", lead_owner=CA), user=CA) is True
	assert portfolio.has_permission(Doc(doctype="Lead", owner="other@x", lead_owner=None), user=CA) is False
	assert portfolio.has_permission(Doc(doctype="Lead", __new=True), user=CA) is True
	assert portfolio.has_permission(Doc(doctype="Company", name="PME Z"), user="admin@x") is True


def test_hooks_do_not_collide_with_staff_isolation():
	assert not set(portfolio.PORTFOLIO_DOCTYPES) & set(ISOLATED_DOCTYPES)


# -- four eyes --


def test_charge_affaires_cannot_decide(world):
	with pytest.raises(Refused, match="validateur"):
		portfolio.check_decision(Doc(doctype="Credit Scoring Dossier", decision="Accord sous conditions"))
	with pytest.raises(Refused, match="validateur"):
		portfolio.check_decision(Doc(doctype="Credit Scoring Dossier", decision="En attente", validator="Moi"))
	with pytest.raises(Refused, match="validateur"):
		portfolio.check_decision(Doc(doctype="Financing Dossier", status="Avis favorable"))


def test_charge_affaires_can_propose(world):
	portfolio.check_decision(Doc(doctype="Credit Scoring Dossier", decision="En attente", ready=1))
	portfolio.check_decision(Doc(doctype="Credit Scoring Dossier", decision=None))
	portfolio.check_decision(Doc(doctype="Financing Dossier", status="En cours d'analyse"))


def test_validator_decides(world, monkeypatch):
	monkeypatch.setattr(frappe, "session", frappe._dict(user="admin@x"), raising=False)
	world["user"] = "admin@x"
	portfolio.check_decision(Doc(doctype="Credit Scoring Dossier", decision="Refus", validator="Admin"))
	portfolio.check_decision(Doc(doctype="Financing Dossier", status="Avis defavorable"))


# -- APIs --


def test_payment_link_refused_outside_the_portfolio(world, monkeypatch):
	monkeypatch.setattr(frappe, "only_for", lambda roles: None, raising=False)
	monkeypatch.setattr(frappe.db, "exists", lambda doctype, name: True, raising=False)
	with pytest.raises(Refused, match="portefeuille"):
		subscription_api.create_company_payment_link("PME Z")


def test_payment_link_allowed_in_the_portfolio(world, monkeypatch):
	monkeypatch.setattr(frappe, "only_for", lambda roles: None, raising=False)
	monkeypatch.setattr(frappe.db, "exists", lambda doctype, name: True, raising=False)
	doc = frappe._dict(name="SUB-1")
	monkeypatch.setattr(subscription_api, "_new_payment", lambda company: doc)
	monkeypatch.setattr(subscription_api, "_create_link", lambda d: "https://pay.jeko.africa/l/1")
	assert subscription_api.create_company_payment_link("PME A")["payment_url"] == "https://pay.jeko.africa/l/1"


def test_guard_portfolio_field(world, monkeypatch):
	class Company(Doc):
		def has_value_changed(self, field):
			return True

	with pytest.raises(Refused, match="administrateur"):
		portfolio.guard_portfolio_field(Company(doctype="Company", name="PME A"))
	monkeypatch.setattr(frappe, "session", frappe._dict(user="admin@x"), raising=False)
	world["user"] = "admin@x"
	portfolio.guard_portfolio_field(Company(doctype="Company", name="PME A"))


# -- declared rights --


def _json(path):
	return json.loads((APP / path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("doctype", ["credit_scoring_dossier", "financing_dossier"])
def test_role_works_the_dossiers_without_deleting(doctype):
	perm = {p["role"]: p for p in _json(f"sitiame_core/doctype/{doctype}/{doctype}.json")["permissions"]}[CHARGE_AFFAIRES_ROLE]
	assert perm["read"] and perm["write"] and perm["create"] and not perm["delete"]


@pytest.mark.parametrize("path", [
	"sitiame_core/page/erp_charge_affaires/erp_charge_affaires.json",
	"sitiame_core/page/erp_financial_ranking/erp_financial_ranking.json",
	"sitiame_core/page/erp_kyc/erp_kyc.json",
	"sitiame_core/page/erp_abonnement/erp_abonnement.json",
	"sitiame_core/report/liasse_syscohada/liasse_syscohada.json",
])
def test_role_opens_its_pages_and_report(path):
	assert CHARGE_AFFAIRES_ROLE in {r["role"] for r in _json(path)["roles"]}


def test_scoring_settings_stay_closed():
	roles = {p["role"] for p in _json("sitiame_core/doctype/scoring_360_settings/scoring_360_settings.json")["permissions"]}
	assert CHARGE_AFFAIRES_ROLE not in roles
