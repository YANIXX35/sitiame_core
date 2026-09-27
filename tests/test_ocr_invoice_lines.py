# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""OCR invoice draft lines (sitiame_core.ocr_invoice._invoice_lines)."""

from sitiame_core.ocr_invoice import _invoice_lines

LINES = [
	{"item_name": "Prestation de conseil informatique", "rate": 250000.0, "qty": 1},
	{"item_name": "Maintenance mensuelle serveur", "rate": 104000.0, "qty": 1},
]


def test_lines_matching_the_ht_are_kept():
	lines, warnings = _invoice_lines(LINES, 354000.0, "FAC-1", "ACME")
	assert [(line["item_name"], line["qty"], line["rate"]) for line in lines] == [
		("Prestation de conseil informatique", 1, 250000.0),
		("Maintenance mensuelle serveur", 1, 104000.0),
	]
	assert warnings == []


def test_lines_contradicting_the_ht_fall_back_to_one_line():
	lines, warnings = _invoice_lines(LINES, 400000.0, "FAC-1", "ACME")
	assert len(lines) == 1 and lines[0]["rate"] == 400000.0 and lines[0]["qty"] == 1
	assert "FAC-1" in lines[0]["item_name"] and "ACME" in lines[0]["item_name"]
	assert len(warnings) == 1 and "354000" in warnings[0]


def test_a_line_without_price_falls_back_to_one_line():
	lines, warnings = _invoice_lines([{"item_name": "Ciment CPJ 45", "qty": 20.0}], 90000.0, "BL-3", "ACME")
	assert len(lines) == 1 and lines[0]["rate"] == 90000.0
	assert len(warnings) == 1


def test_no_table_read_is_one_line_without_warning():
	lines, warnings = _invoice_lines([], 118000.0, "F-2", "ACME")
	assert len(lines) == 1 and lines[0]["rate"] == 118000.0
	assert warnings == []


def test_quantities_are_multiplied():
	items = [
		{"item_name": "Carton tomates 5kg", "qty": 10.0, "rate": 4500.0},
		{"item_name": "Oignons sac", "qty": 2.0, "rate": 12000.0},
	]
	lines, warnings = _invoice_lines(items, 69000.0, "F-3", "ACME")
	assert len(lines) == 2 and warnings == []
