# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""A scanned invoice imported on the wrong side (sitiame_core.ocr_invoice
._check_direction): SITIAME's own sales invoice imported as a purchase
created "SITIAME CAPITAL SARL" as SITIAME's own supplier (2026-09-28)."""

import frappe
import pytest

from sitiame_core import ocr_invoice


@pytest.fixture(autouse=True)
def company(monkeypatch):
	monkeypatch.setattr(frappe, "get_cached_value", lambda doctype, name, field: "SITIAME", raising=False)


OWN_SALES_INVOICE = {"supplier_name": "SITIAME CAPITAL SARL", "customer_name": "Entreprise Kouassi et Fils"}
SUPPLIER_INVOICE = {"supplier_name": "TechServices Cote d Ivoire SARL", "customer_name": "SITIAME CAPITAL SARL"}


def test_own_sales_invoice_imported_as_a_purchase_is_refused():
	with pytest.raises(frappe.ValidationError, match="Factures de vente"):
		ocr_invoice._check_direction(True, OWN_SALES_INVOICE, "SITIAME")


def test_supplier_invoice_imported_as_a_sale_is_refused():
	with pytest.raises(frappe.ValidationError, match="Factures d'achat"):
		ocr_invoice._check_direction(False, SUPPLIER_INVOICE, "SITIAME")


def test_right_side_imports_pass():
	ocr_invoice._check_direction(True, SUPPLIER_INVOICE, "SITIAME")
	ocr_invoice._check_direction(False, OWN_SALES_INVOICE, "SITIAME")


def test_a_supplier_sharing_a_word_with_the_company_is_not_refused():
	"""Company "yao" buying from "Yao Transport": the customer printed on the
	invoice is the company itself, so nothing is refused."""
	fields = {"supplier_name": "Yao Transport SARL", "customer_name": "YAO"}
	ocr_invoice._check_direction(True, fields, "yao")


def test_missing_party_is_not_refused():
	ocr_invoice._check_direction(True, {"supplier_name": "SITIAME CAPITAL SARL"}, "SITIAME")
