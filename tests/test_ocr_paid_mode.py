# Copyright (c) 2026, Sitiame Capital
# License: MIT

""""Facture deja payee" on the OCR review screen marks the draft so that
its Payment Entry is created at validation (ocr_invoice._apply_payment)."""

import frappe
import pytest

from sitiame_core import ocr_invoice


@pytest.fixture(autouse=True)
def modes(monkeypatch):
	monkeypatch.setattr(frappe.db, "exists", lambda doctype, name=None: name in ("Cash", "Wave"), raising=False)


def test_paid_invoice_is_marked_for_its_payment():
	invoice = frappe._dict()
	ocr_invoice._apply_payment(invoice, "Wave")
	assert invoice.sitiame_pay_on_submit == 1 and invoice.sitiame_payment_mode == "Wave"


def test_unpaid_invoice_is_left_alone():
	invoice = frappe._dict()
	ocr_invoice._apply_payment(invoice, None)
	assert "sitiame_pay_on_submit" not in invoice


def test_unknown_mode_is_refused():
	with pytest.raises(frappe.ValidationError, match="Moyen de paiement inconnu"):
		ocr_invoice._apply_payment(frappe._dict(), "Bitcoin")
