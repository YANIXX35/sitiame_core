# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Scanned purchase invoices (2026-10-15 test imports): parts billed with a
maintenance, equipment and furniture against the company's fixed-asset
threshold, and the party's memory no longer overriding recognised lines."""

import pytest

from sitiame_core import ocr_accounts as oa

# the chart and helpers of the plan tests (autouse fixture included)
from tests.test_ocr_plan import acc, by_account, chart, plan, taxes  # noqa: F401


def test_parts_billed_with_a_maintenance_follow_it():
	"""CIE ENERGIE PRO TEST: the filters went to 6011 (goods for resale)."""
	fields = {"invoice_date": "2025-01-17", "subtotal": 175500, "tax_amount": 31590, "grand_total": 207090}
	lines = [
		{"item_name": "Maintenance groupe électrogène", "qty": 1, "rate": 120000},
		{"item_name": "Pièces de rechange (filtres)", "qty": 3, "rate": 18500},
	]
	assert by_account(plan(fields, lines)) == {"6243": 120000, "6242": 55500}


def test_cleaning_products_are_not_a_repair():
	assert not oa.is_repair("Produits d'entretien et détergents")
	assert oa.is_repair("Entretien climatiseur")


@pytest.mark.parametrize(
	"label, number",
	[
		("Ordinateur portable Core i5 16Go", "2442"),
		("Ecran 24 pouces", "2442"),
		("Imprimante laser couleur", "2443"),
		("Photocopieur multifonction", "2443"),
		("Chaises de bureau ergonomiques", "2444"),
		("Bureau 160 cm", "2444"),
		("Armoire métallique", "2444"),
		("Climatiseur split 1,5 CV", "2441"),
		("Fournitures de bureau", None),
		("Loyer bureau octobre", None),
	],
)
def test_equipment_accounts(label, number):
	assert oa.equipment_account_number(label) == number


def test_equipment_below_the_threshold_is_small_equipment():
	"""Default threshold 500 000 FCFA per unit (no Company field here)."""
	fields = {"invoice_date": "2025-05-09", "subtotal": 550000, "tax_amount": 99000, "grand_total": 649000}
	lines = [
		{"item_name": "Chaises de bureau ergonomiques", "qty": 4, "rate": 65000},
		{"item_name": "Bureau 160 cm", "qty": 2, "rate": 145000},
	]
	result = plan(fields, lines)
	assert by_account(result) == {"6056": 550000}
	assert not any("Immobilisation" in w for w in result["warnings"])


def test_equipment_above_the_threshold_is_a_flagged_fixed_asset():
	fields = {"invoice_date": "2024-07-05", "subtotal": 1250000, "tax_amount": 225000, "grand_total": 1475000}
	lines = [
		{"item_name": "Ordinateur portable Core i7 32Go", "qty": 2, "rate": 600000},
		{"item_name": "Licence antivirus 1 an", "qty": 2, "rate": 25000},
	]
	result = plan(fields, lines)
	assert by_account(result)["2442"] == 1200000  # the licence is not equipment
	asset = next(line for line in result["lines"] if line["account_number"] == "2442")
	assert asset["source"] == "immobilisation"
	assert any("Immobilisation probable" in w and "Ordinateur portable" in w for w in result["warnings"])
	assert "4451" in taxes(result)


def test_threshold_is_read_per_unit_on_the_company(monkeypatch):
	monkeypatch.setattr(oa, "asset_threshold", lambda company: 100000)
	fields = {"invoice_date": "2025-05-09", "subtotal": 290000, "grand_total": 290000}
	result = plan(fields, [{"item_name": "Bureau 160 cm", "qty": 2, "rate": 145000}])
	assert by_account(result) == {"2444": 290000}


def test_memory_only_fills_the_lines_keywords_miss():
	"""BUREAU PLUS CI TEST's last invoice started on 6327: its next invoice
	went entirely to 6327, office supplies included."""
	fields = {"invoice_date": "2025-05-09", "subtotal": 100000, "grand_total": 100000}
	lines = [
		{"item_name": "Ramettes papier A4", "qty": 10, "rate": 5000},
		{"item_name": "Article non reconnu", "qty": 1, "rate": 50000},
	]
	result = plan(fields, lines, remembered=acc("6327"))
	assert by_account(result) == {"6047": 50000, "6327": 50000}
	assert [line["source"] for line in result["lines"]] == ["mot-cle", "memoire"]
