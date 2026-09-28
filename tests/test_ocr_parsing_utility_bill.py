# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Real OCR.space output of a CIE electricity bill (WhatsApp photo,
2026-09-28): the OCR fallback found no amount ("MONTANTAREGLER: 374 400"
wasn't a known label), took "CHERS CLIENTS, ..." as the customer and the
whole legal line as the supplier."""

from pathlib import Path

from sitiame_core import api

TEXT = (Path(__file__).parent / "fixtures" / "cie_electricity_bill_ocr.txt").read_text(encoding="utf-8")


def test_amount_to_settle_is_read_even_glued_together():
	fields, _ = api._extract_invoice_fields(TEXT)
	assert fields["grand_total"] == 374400.0


def test_a_label_with_nothing_after_it_does_not_take_the_next_line():
	fields, _ = api._extract_invoice_fields(TEXT)
	assert "customer_name" not in fields


def test_letterhead_stops_before_the_legal_mentions():
	fields, _ = api._extract_invoice_fields(TEXT)
	assert fields["supplier_name"] == "COMPAGNIE IVOIRIENNE D'ELECTRICITE"


def test_client_label_on_the_same_line_still_works():
	fields, _ = api._extract_invoice_fields("FACTURE\nClient : BOUTIQUE AMANI SARL\n")
	assert fields["customer_name"] == "BOUTIQUE AMANI SARL"
