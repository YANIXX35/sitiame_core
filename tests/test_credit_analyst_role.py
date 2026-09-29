# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""The "Analyste Credit Sitiame" role opens the Scoring and Financement
modules to staff who are not System Manager (2026-09-29: a staff account
with the standard role bundle saw neither module)."""

import json
import pathlib

import frappe
import pytest

from sitiame_core import api
from sitiame_core.roles import CREDIT_ANALYST_ROLE

APP = pathlib.Path(__file__).resolve().parents[1] / "sitiame_core" / "sitiame_core"


def _perms(path, key="permissions"):
	return {p["role"]: p for p in json.loads((APP / path).read_text(encoding="utf-8"))[key]}


@pytest.mark.parametrize("doctype", ["credit_scoring_dossier", "financing_dossier"])
def test_the_role_works_the_dossiers(doctype):
	perm = _perms(f"doctype/{doctype}/{doctype}.json")[CREDIT_ANALYST_ROLE]
	assert perm["read"] and perm["write"] and perm["create"]
	assert not perm["delete"]


def test_the_role_reads_the_scoring_settings_without_changing_them():
	perm = _perms("doctype/scoring_360_settings/scoring_360_settings.json")[CREDIT_ANALYST_ROLE]
	assert perm["read"] and not perm["write"]


def test_the_role_opens_the_financial_ranking_page():
	assert CREDIT_ANALYST_ROLE in _perms("page/erp_financial_ranking/erp_financial_ranking.json", "roles")


@pytest.fixture
def roles(monkeypatch):
	state = {"roles": []}
	monkeypatch.setattr(frappe, "get_roles", lambda user=None: state["roles"], raising=False)
	return state


def test_ranking_endpoint_accepts_the_role(roles, monkeypatch):
	allowed = []
	monkeypatch.setattr(frappe, "only_for", lambda r, message=False: allowed.append(r), raising=False)
	monkeypatch.setattr("sitiame_core.scoring360_service.classement_erpnext", lambda a, b: [], raising=False)
	api.get_financial_ranking()
	assert CREDIT_ANALYST_ROLE in allowed[0]


class Refused(Exception):
	pass


def _throw(msg, exc=None):
	raise Refused(msg)


def test_other_staff_is_still_refused_the_scoring_suggestions(roles, monkeypatch):
	monkeypatch.setattr(frappe, "throw", _throw, raising=False)
	roles["roles"] = ["Accounts Manager"]
	with pytest.raises(Refused, match="analystes"):
		api.get_scoring_suggestions("S")
