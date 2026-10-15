# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""The 'Liasse fiscale' tile: SYSCOHADA statements for Sitiame staff only."""

import importlib
import json
import pathlib

import frappe
import pytest

from sitiame_core import boot, liasse_fiscale as lf

REPORTS = pathlib.Path(lf.__file__).parent / "sitiame_core" / "report"


def _folder(name):
	return REPORTS / name.lower().replace(" ", "_")


@pytest.mark.parametrize("name", sorted(lf.STATEMENT_REPORTS))
def test_each_statement_is_a_standard_report(name):
	slug = _folder(name).name
	meta = json.loads((_folder(name) / f"{slug}.json").read_text(encoding="utf-8"))
	assert meta["name"] == meta["report_name"] == name
	assert meta["is_standard"] == "Yes" and meta["report_type"] == "Script Report"
	assert "PME Client" not in {r["role"] for r in meta["roles"]}
	assert f'frappe.query_reports["{name}"]' in (_folder(name) / f"{slug}.js").read_text(encoding="utf-8")


def test_statements_are_the_liasse_ones():
	from sitiame_core.sitiame_core.report.liasse_syscohada import liasse_syscohada

	assert set(lf.STATEMENT_REPORTS.values()) == set(liasse_syscohada.STATEMENTS)


@pytest.mark.parametrize("name", sorted(lf.STATEMENT_REPORTS))
def test_report_runs_its_statement(monkeypatch, name):
	monkeypatch.setattr(frappe, "get_roles", lambda user=None: ["Personnel Sitiame"], raising=False)
	seen = {}
	liasse = importlib.import_module("sitiame_core.sitiame_core.report.liasse_syscohada.liasse_syscohada")
	monkeypatch.setattr(liasse, "execute", lambda f: seen.setdefault("filters", f) and "ok")
	mod = importlib.import_module(f"sitiame_core.sitiame_core.report.{_folder(name).name}.{_folder(name).name}")
	assert mod.execute({"company": "SITIAME", "fiscal_year": "2026"}) == "ok"
	assert seen["filters"].statement == lf.STATEMENT_REPORTS[name]
	assert seen["filters"].company == "SITIAME"


def test_pme_account_is_refused_even_by_url(monkeypatch):
	monkeypatch.setattr(frappe, "get_roles", lambda user=None: ["PME Client", "Accounts Manager"], raising=False)
	with pytest.raises(Exception):
		lf.run_statement("Bilan actif SYSCOHADA", {"company": "X", "fiscal_year": "2026"})


def test_tile_lists_every_statement_and_is_hidden_from_pmes():
	reports = {to for _, kind, to in lf.SIDEBAR_ITEMS if kind == "Report"}
	assert set(lf.STATEMENT_REPORTS) <= reports
	assert lf.TILE in boot._PME_HIDDEN_LABELS
