# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""ERPNext's standard statements fed by the SYSCOHADA liasse
(Financial Report Templates, syscohada_templates.py)."""

import re

import frappe
import pytest

from sitiame_core import hooks, syscohada_templates as st
from sitiame_core.syscohada_statements import ACTIF_LINES, PASSIF_LINES, RESULTAT_ORDER
from tests.test_syscohada_tafire import _make_statements, _patch_tafire


@pytest.mark.parametrize("report", sorted(st.TEMPLATES))
def test_reference_codes_are_unique_and_valid(report):
	codes = [r["reference_code"] for r in st.template_rows(report) if r["data_source"] == "Custom API"]
	assert len(codes) == len(set(codes))
	assert all(re.match(r"^[A-Za-z][A-Za-z0-9_]*$", c) for c in codes)
	assert all(r["calculation_formula"] == st.API for r in st.template_rows(report) if r["data_source"] == "Custom API")


def test_every_liasse_line_is_in_a_template():
	bilan = {r["reference_code"] for r in st.template_rows("Balance Sheet") if r.get("reference_code")}
	assert bilan == {f"A_{c}" for c, *_r in ACTIF_LINES} | {f"P_{c}" for c, *_r in PASSIF_LINES}
	resultat = [r["reference_code"] for r in st.template_rows("Profit and Loss Statement")]
	assert resultat == [f"R_{c}" for c in RESULTAT_ORDER]


def test_tafire_lines_follow_compute_tafire(monkeypatch):
	_patch_tafire(monkeypatch, _make_statements(), _make_statements())
	rows = st.compute_tafire("TEST", "2026-01-01", "2026-12-31")["rows"]
	assert [(r["ref"], r["libelle"], bool(r["bold"])) for r in rows] == st.TAFIRE_LINES


@pytest.fixture
def ledger(monkeypatch):
	monkeypatch.setattr(frappe, "local", type("L", (), {})(), raising=False)
	monkeypatch.setattr(frappe, "has_permission", lambda *a, **k: True, raising=False)
	monkeypatch.setattr(st, "_year_start", lambda company, date: st.getdate("2026-01-01"))
	calls = []

	def fake(company, from_date, to_date):
		calls.append((str(from_date), str(to_date)))
		return {"actif_net": {"BZ": 100.0}, "passif": {"CA": 70.0}, "resultat": {"XZ": 30.0}}

	monkeypatch.setattr(st, "compute_statements", fake)
	return calls


PERIODS = [{"from_date": "2026-01-01", "to_date": "2026-06-30"}, {"from_date": "2026-07-01", "to_date": "2026-12-31"}]


def test_line_reads_its_side_and_code(ledger):
	f = {"company": "SITIAME"}
	assert st.line(f, PERIODS, {"reference_code": "A_BZ"}) == [100.0, 100.0]
	assert st.line(f, PERIODS, {"reference_code": "P_CA"}) == [70.0, 70.0]
	assert st.line(f, PERIODS, {"reference_code": "R_XZ"}) == [30.0, 30.0]
	assert len(ledger) == 2  # one computation per period, shared by the lines


def test_income_statement_per_period_when_not_accumulated(ledger):
	st.line({"company": "SITIAME", "accumulated_values": 0}, PERIODS, {"reference_code": "R_XZ"})
	assert ledger == [("2026-01-01", "2026-06-30"), ("2026-07-01", "2026-12-31")]


def test_balance_sheet_is_always_from_the_year_start(ledger):
	st.line({"company": "SITIAME", "accumulated_values": 0}, PERIODS, {"reference_code": "A_BZ"})
	assert ledger == [("2026-01-01", "2026-06-30"), ("2026-01-01", "2026-12-31")]


def test_company_permission_is_checked(monkeypatch, ledger):
	def deny(*a, **k):
		raise frappe.PermissionError

	monkeypatch.setattr(frappe, "has_permission", deny, raising=False)
	with pytest.raises(frappe.PermissionError):
		st.line({"company": "AUTRE"}, PERIODS, {"reference_code": "A_BZ"})


def test_report_page_script_is_loaded():
	assert "/assets/sitiame_core/js/syscohada_statements.js" in hooks.app_include_js
