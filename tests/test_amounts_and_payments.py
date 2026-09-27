# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""HT/TVA/TTC reconciliation for OCR drafts, receipt parsing, CinetPay phone."""

import frappe
import pytest

from sitiame_core import ocr_payment
from sitiame_core.cinetpay_client import normalize_phone
from sitiame_core.ocr_invoice import _resolve_amounts


class TestResolveAmounts:
	def test_consistent_invoice(self):
		net, tax, warnings = _resolve_amounts({"subtotal": 354000, "tax_amount": 63720, "grand_total": 417720})
		assert (net, tax, warnings) == (354000, 63720, [])

	def test_misread_vat_is_recomputed_from_ht_and_ttc(self):
		"""The rate "18" read as the VAT amount must not reach the invoice."""
		net, tax, warnings = _resolve_amounts({"subtotal": 354000, "tax_amount": 18, "grand_total": 417720})
		assert (net, tax) == (354000, 63720)
		assert warnings

	def test_missing_ht_derived_from_ttc_minus_vat(self):
		net, tax, _ = _resolve_amounts({"tax_amount": 18000, "grand_total": 118000})
		assert (net, tax) == (100000, 18000)

	def test_ttc_only_is_booked_without_vat_and_flagged(self):
		net, tax, warnings = _resolve_amounts({"grand_total": 50000})
		assert (net, tax) == (50000, 0)
		assert warnings

	def test_no_amount_at_all_is_refused(self):
		with pytest.raises(frappe.ValidationError):
			_resolve_amounts({})


@pytest.mark.parametrize(
	"raw, expected",
	[
		("0143875302", "+2250143875302"),  # local format: CinetPay FAILED it (ER-P-...)
		("01 43 87 53 02", "+2250143875302"),
		("+2250509273117", "+2250509273117"),
		("002250747931239", "+2250747931239"),
		("2250747931239", "+2250747931239"),
		("+33612345678", "+33612345678"),
		("12345", None),  # not fixable: left out rather than breaking the link
		(None, None),
	],
)
def test_cinetpay_phone_format(raw, expected):
	assert normalize_phone(raw) == expected


class TestReceiptParsing:
	def test_paid_amount_label(self):
		assert ocr_payment._read_paid_amount("Montant paye : 417 720 FCFA", {}) == 417720.0

	def test_grand_total_field_wins(self):
		assert ocr_payment._read_paid_amount("Montant : 1 000", {"grand_total": 5000}) == 5000.0

	@pytest.mark.parametrize(
		"line, expected",
		[
			("ID transaction : T_8XK2P9Q4", "T_8XK2P9Q4"),
			("Référence : CI240926.1512.A73821", "CI240926.1512.A73821"),
			("Transaction ID: MP260924.1433.C12345", "MP260924.1433.C12345"),
			("Reference de paiement : ABCDEF", None),  # no digit: not an id
			("Objet : reglement facture FAC-2026-001", None),
		],
	)
	def test_transaction_id(self, line, expected):
		assert ocr_payment._read_transaction_id(line) == expected

	@pytest.mark.parametrize(
		"text, mode",
		[
			("Wave - Recu de paiement", "Wave"),
			("Orange Money transfert", "Orange Money"),
			("MTN MoMo CI", "MTN MoMo"),
			("Paiement Moov Flooz", "Moov Money"),
			("Remise de chèque", "Cheque"),
			("Avis de virement bancaire", "Wire Transfer"),
			("Reçu de caisse, espèces", "Cash"),
			("Wave virement", "Wave"),  # brand wins over the generic word
			("Reçu sans indication", None),
		],
	)
	def test_mode_of_payment(self, monkeypatch, text, mode):
		monkeypatch.setattr(frappe.db, "exists", lambda doctype, name=None: True, raising=False)
		assert ocr_payment._detect_mode_of_payment(text) == mode


def test_phone_mode_without_linked_account_uses_the_mobile_money_account(monkeypatch):
	"""Only SITIAME had Wave/Orange/MTN/Moov linked: elsewhere a Mobile
	Money receipt fell back to the 5211 bank account."""

	def get_value(doctype, filters, fieldname=None, **kwargs):
		if doctype == "Mode of Payment" and fieldname == "type":
			return "Phone"
		return None

	monkeypatch.setattr(frappe.db, "get_value", get_value, raising=False)
	monkeypatch.setattr(ocr_payment, "mobile_money_account", lambda company, mode: f"552 - MM - {company}", raising=False)
	assert ocr_payment._mode_account("Wave", "YAO") == "552 - MM - YAO"
