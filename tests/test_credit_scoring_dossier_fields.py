# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""The Scoring 360 panel section of Credit Scoring Dossier: fields exist,
sit between "Le dossier" and the company info, and the DocType's modified
timestamp moved (bench migrate skips a DocType JSON whose modified didn't
change)."""

import json
from pathlib import Path

DOCTYPE = (
	Path(__file__).resolve().parents[1]
	/ "sitiame_core/sitiame_core/doctype/credit_scoring_dossier/credit_scoring_dossier.json"
)

NEW_FIELDS = [
	("scoring360_section", "Section Break"),
	("scoring_period_from", "Date"),
	("scoring_period_col", "Column Break"),
	("scoring_period_to", "Date"),
	("scoring360_panel_break", "Section Break"),
	("scoring360_panel", "HTML"),
]


def _doctype():
	return json.loads(DOCTYPE.read_text(encoding="utf-8"))


def test_new_fields_are_defined_with_their_types():
	fields = {f["fieldname"]: f for f in _doctype()["fields"]}
	for fieldname, fieldtype in NEW_FIELDS:
		assert fields[fieldname]["fieldtype"] == fieldtype


def test_new_fields_sit_between_purpose_and_company_info():
	order = _doctype()["field_order"]
	start = order.index("purpose") + 1
	assert order[start : start + len(NEW_FIELDS)] == [name for name, _ in NEW_FIELDS]
	assert order[start + len(NEW_FIELDS)] == "company_info_section"


def test_modified_was_bumped_so_migrate_applies_it():
	assert _doctype()["modified"] > "2026-09-18 00:00:00.000000"
