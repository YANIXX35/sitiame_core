# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""get_scoring360_score: company-scoped access (a PME only reads its own
company, via its Company User Permission) and the extra keys the Credit
Scoring Dossier panel needs (entries_count, config)."""

import frappe
import pytest

from sitiame_core import api
from sitiame_core import scoring360_service as svc

CONFIG = {
	"coefficients": {"strong": 1.0, "medium": 0.6, "weak": 0.2},
	"bank": {
		"weights": {"dscr": 25},
		"thresholds": {"dscr": {"strong": 1.5, "medium": 1.1, "direction": "gte"}},
		"decision": {"strong_min": 80, "medium_min": 60, "labels": {}, "lectures": {}},
	},
	"investor": {
		"weights": {"roe": 20},
		"thresholds": {"roe": {"strong": 0.15, "medium": 0.08, "direction": "gte"}},
		"decision": {"strong_min": 80, "medium_min": 60, "labels": {}, "lectures": {}},
	},
	"internal": {
		"weights": {"receivable_days": 20},
		"thresholds": {"receivable_days": {"strong": 45, "medium": 60, "direction": "lte"}},
		"decision": {"strong_min": 80, "medium_min": 60, "labels": {}, "lectures": {}},
	},
	"composite": {
		"weights": {"bank": 40, "investor": 35, "internal": 25},
		"decision": {"strong_min": 80, "medium_min": 60, "labels": {}, "lectures": {}},
	},
}

SCORE = {
	"period": {"from": "2025-09-28", "to": "2026-09-27"},
	"ratios": {"dscr": 2.0},
	"blocks": {"bank": {"total": 90.0}, "investor": {"total": 50.0}, "internal": {"total": 70.0}},
	"composite": {"total": 71.0},
	"inputs": {"revenue": 1000.0},
}


@pytest.fixture
def engine(monkeypatch):
	calls = {"permission": [], "score": []}

	def has_permission(doctype, ptype, doc, throw=False):
		calls["permission"].append((doctype, ptype, doc, throw))
		if doc != "PME A":
			raise frappe.PermissionError("not allowed")
		return True

	def score_company(company, date_from=None, date_to=None):
		calls["score"].append((company, date_from, date_to))
		return dict(SCORE)

	monkeypatch.setattr(frappe, "has_permission", has_permission, raising=False)
	monkeypatch.setattr(svc, "_entries_count", lambda company, date_from=None, date_to=None: 12)
	monkeypatch.setattr(svc, "score_company", score_company)
	monkeypatch.setattr(svc, "get_config", lambda: CONFIG)
	return calls


def test_checks_read_permission_on_the_company(engine):
	api.get_scoring360_score("PME A")
	assert engine["permission"] == [("Company", "read", "PME A", True)]


def test_other_company_is_refused_before_any_computation(engine):
	with pytest.raises(frappe.PermissionError):
		api.get_scoring360_score("PME B")
	assert engine["score"] == []


def test_keeps_engine_output_and_adds_entries_count_and_config(engine):
	result = api.get_scoring360_score("PME A", "2025-09-28", "2026-09-27")

	for key in ("period", "ratios", "blocks", "composite", "inputs"):
		assert result[key] == SCORE[key]
	assert result["entries_count"] == 12
	assert result["config"]["bank"]["weights"] == {"dscr": 25}
	assert result["config"]["internal"]["thresholds"]["receivable_days"]["direction"] == "lte"
	assert result["config"]["composite"] == {"weights": {"bank": 40, "investor": 35, "internal": 25}}
	assert "decision" not in result["config"]["bank"]


def test_empty_dates_are_passed_as_none(engine):
	api.get_scoring360_score("PME A", "", "")
	assert engine["score"] == [("PME A", None, None)]


def test_no_entries_returns_only_the_count(engine, monkeypatch):
	monkeypatch.setattr(svc, "_entries_count", lambda company, date_from=None, date_to=None: 0)
	assert api.get_scoring360_score("PME A") == {"entries_count": 0}
	assert engine["score"] == []
