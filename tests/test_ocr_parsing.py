# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""OCR text -> structured invoice fields (sitiame_core.api)."""

import pytest

from sitiame_core import api

# Verbatim OCR.space output for Facture_Propre_Test.jpg (2026-09-24): tab
# separated cells, labels without colons, "TVA 18 percent".
REAL_OCR_TEXT = (
	"TechServices Cote d Ivoire SARL\tFACTURE\t\r\n"
	"Cocody Riviera Palmeraie Abidjan\tN FAC-2026-0512\t\r\n"
	"RCCM CI-ABJ-2019-B-12345\t\r\n"
	"NIF 1234567X\t\r\n"
	"Date 20/08/2026\t\r\n"
	"Client SITIAME CAPITAL SARL\t\r\n"
	"Adresse Plateau Abidjan\t\r\n"
	"Designation\tMontant\t\r\n"
	"Prestation de conseil informatique\t250 000 FCFA\t\r\n"
	"Maintenance mensuelle serveur\t104 000 FCFA\t\r\n"
	"Montant HT\t354 000 FCFA\t\r\n"
	"TVA 18 percent 63 720 FCFA\t\r\n"
	"Montant TTC 417 720 FCFA\t\r\n"
	"Echeance 19/09/2026\t\r\n"
	"Merci de votre confiance"
)


# Verbatim OCR.space output for facture-test.pdf (2026-09-27): no VAT,
# "TOTAL A PAYER", "Description" header, and the "Qte" header cell lost by
# the OCR (rows keep 4 cells under a 3-cell header).
REAL_OCR_TEXT_NO_VAT = (
	"SITIAME CAPITAL SARL\t\r\n"
	"Facture N: FAC-2026-0042\t\r\n"
	"Date: 17/09/2026\t\r\n"
	"Client : Entreprise Kouassi et Fils\t\r\n"
	"Adresse : Abidjan, Cocody Riviera\t\r\n"
	"Description\tPrix unitaire\tMontant\t\r\n"
	"Prestation de conseil comptable\t1\t250 000\t250 000\t\r\n"
	"Licence logiciel annuelle\t1\t150 000\t150 000\t\r\n"
	"TOTAL A PAYER : 400 000 FCFA"
)


@pytest.mark.parametrize(
	"label", ["TOTAL A PAYER : 400 000", "Total à payer 400 000", "NET À PAYER : 400 000", "Net a payer 400 000"]
)
def test_amount_to_pay_is_the_grand_total(label):
	fields, _ = api._extract_invoice_fields(label + " FCFA\n")
	assert fields["grand_total"] == 400000.0


def test_real_no_vat_invoice_reads_its_total():
	fields, _ = api._extract_invoice_fields(REAL_OCR_TEXT_NO_VAT)
	assert fields["grand_total"] == 400000.0
	assert "subtotal" not in fields and "tax_amount" not in fields


def test_real_scan_reads_all_nine_fields():
	fields, confidence = api._extract_invoice_fields(REAL_OCR_TEXT)
	assert fields == {
		"invoice_number": "FAC-2026-0512",
		"invoice_date": "2026-08-20",
		"due_date": "2026-09-19",
		"supplier_name": "TechServices Cote d Ivoire SARL",
		"customer_name": "SITIAME CAPITAL SARL",
		"tax_id": "1234567X",
		"subtotal": 354000.0,
		"tax_amount": 63720.0,
		"grand_total": 417720.0,
	}
	# the letterhead guess is flagged as less certain than a labelled field
	assert confidence["supplier_name"] < confidence["invoice_number"]


def test_vat_rate_is_not_taken_for_the_vat_amount():
	"""Regression: "TVA 18 percent 63 720" used to yield tax_amount=18."""
	fields, _ = api._extract_invoice_fields("TVA 18 percent 63 720 FCFA\n")
	assert fields["tax_amount"] == 63720.0


def test_letterhead_drops_the_facture_heading_cell():
	"""Regression: supplier was "TechServices ... SARL\\tFACTURE"."""
	assert api._guess_supplier_from_letterhead("ACME SARL\tFACTURE\t\nautre") == "ACME SARL"


def test_classic_labelled_layout_still_works():
	text = (
		"ACME SARL\nFacture N° : F-2026-77\nDate de facture : 01/09/2026\n"
		"Fournisseur : ACME SARL\nNIF : 99887766\nTotal HT : 100 000\n"
		"TVA (18%) : 18 000\nTotal TTC : 118 000\nDate d'échéance : 30/09/2026"
	)
	fields, _ = api._extract_invoice_fields(text)
	assert fields["invoice_number"] == "F-2026-77"
	assert fields["invoice_date"] == "2026-09-01"
	assert fields["due_date"] == "2026-09-30"
	assert (fields["subtotal"], fields["tax_amount"], fields["grand_total"]) == (100000.0, 18000.0, 118000.0)


def test_nif_line_is_not_read_as_an_invoice_number():
	fields, _ = api._extract_invoice_fields("NIF 1234567X\nNCC 7654321\n")
	assert "invoice_number" not in fields


@pytest.mark.parametrize(
	"raw, expected",
	[
		("417 720", 417720.0),
		("1.234.567,89", 1234567.89),
		("1,234,567.89", 1234567.89),
		("500.000", 500000.0),  # FCFA: 3 digits after a single separator = thousands
		("12.50", 12.5),
		("", None),
	],
)
def test_parse_amount(raw, expected):
	assert api._parse_amount(raw) == expected


class TestLineItems:
	def test_tab_separated_rows_are_read(self):
		"""Regression: cells were split on 2+ spaces only, so OCR.space's
		tab-separated tables never produced a single row."""
		items = api._extract_line_items(REAL_OCR_TEXT)
		assert items == [
			{"item_name": "Prestation de conseil informatique", "rate": 250000.0, "qty": 1},
			{"item_name": "Maintenance mensuelle serveur", "rate": 104000.0, "qty": 1},
		]

	def test_quantity_and_unit_price_columns(self):
		text = (
			"Désignation\tQté\tPrix unitaire\tMontant\n"
			"Carton tomates 5kg\t10\t4 500\t45 000\n"
			"Oignons sac 25kg\t2\t12 000\t24 000\n"
			"Total HT\t69 000\n"
		)
		assert api._extract_line_items(text) == [
			{"item_name": "Carton tomates 5kg", "qty": 10.0, "rate": 4500.0},
			{"item_name": "Oignons sac 25kg", "qty": 2.0, "rate": 12000.0},
		]

	def test_space_aligned_delivery_note(self):
		text = "Designation  Reference  Qte  Unite\nCiment CPJ 45  CIM-45  20  sac\n\n"
		assert api._extract_line_items(text) == [{"item_name": "Ciment CPJ 45", "qty": 20.0}]

	def test_description_header_and_lost_header_cell(self):
		"""The OCR dropped the "Qte" header cell: numbers are right-aligned,
		so the unit price must not be read from the quantity column."""
		assert api._extract_line_items(REAL_OCR_TEXT_NO_VAT) == [
			{"item_name": "Prestation de conseil comptable", "qty": 1.0, "rate": 250000.0},
			{"item_name": "Licence logiciel annuelle", "qty": 1.0, "rate": 150000.0},
		]

	def test_libelle_header(self):
		text = "Libellé\tMontant\nLoyer septembre\t300 000\n\n"
		assert api._extract_line_items(text) == [{"item_name": "Loyer septembre", "rate": 300000.0, "qty": 1}]

	def test_trailing_currency_cell_keeps_the_unshifted_columns(self):
		text = "Designation\tMontant\nLoyer septembre\t300 000\tFCFA\n\n"
		assert api._extract_line_items(text) == [{"item_name": "Loyer septembre", "rate": 300000.0, "qty": 1}]

	def test_no_table_header(self):
		assert api._extract_line_items("juste du texte\nsans tableau") == []


def test_document_type_detection():
	assert api._detect_document_type("FACTURE N 12", {}) == "invoice"
	assert api._detect_document_type("DEVIS numéro 4", {}) == "quotation"
	assert api._detect_document_type("Bon de commande 8", {}) == "purchase_order"
