# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Review screen: the scan is read without creating anything, the user
corrects/completes the fields, and the draft is built from the validated
values -- an unreadable party or total no longer blocks the import."""

import frappe
import pytest

from sitiame_core import ocr_invoice

READING = {
	"source": "vision",
	"document_type": "invoice",
	"fields": {"invoice_number": "FA-12", "supplier_name": "TRACTAFRIC", "customer_name": "SITIAME", "grand_total": 287634.0},
	"confidence": {"invoice_number": 1.0, "supplier_name": 0.9, "customer_name": 1.0, "grand_total": 0.3},
	"line_items": [{"item_name": "Pieces", "qty": 1, "rate": 5.0}],
	"warnings": ["HT + TVA ne font pas le TTC"],
	"text": "",
}


class Cache(dict):
	def set_value(self, key, value, expires_in_sec=None):
		self[key] = value

	def get_value(self, key):
		return self.get(key)

	def delete_value(self, key):
		self.pop(key, None)


@pytest.fixture
def env(monkeypatch):
	cache = Cache()
	reads = []

	def read(file_url):
		reads.append(file_url)
		return {k: (dict(v) if isinstance(v, dict) else v) for k, v in READING.items()}

	monkeypatch.setattr(frappe, "cache", lambda: cache, raising=False)
	monkeypatch.setattr(frappe, "session", frappe._dict(user="yanisse@x.com"), raising=False)
	monkeypatch.setattr(ocr_invoice, "read_invoice_file", read)
	monkeypatch.setattr(ocr_invoice, "_check_direction", lambda *a: None)
	monkeypatch.setattr(ocr_invoice, "_find_party", lambda party_type, name: "TRACTAFRIC MOTORS" if name == "TRACTAFRIC" else None)
	return frappe._dict(cache=cache, reads=reads)


def test_review_reads_without_creating_and_keeps_the_reading(env):
	review = ocr_invoice.ocr_read_invoice_for_review("/private/files/f.jpg", "Purchase Invoice", "SITIAME")
	assert review["fields"]["grand_total"] == 287634.0
	assert review["fields"]["subtotal"] is None  # every reviewable field is listed
	assert review["confidence"]["grand_total"] == 0.3
	assert review["warnings"] == ["HT + TVA ne font pas le TTC"]
	assert review["party_key"] == "supplier_name"
	assert review["existing_party"] == "TRACTAFRIC MOTORS"
	assert env.cache[ocr_invoice._review_cache_key("/private/files/f.jpg")]["source"] == "vision"


def test_review_of_a_non_invoice_warns_instead_of_refusing(env, monkeypatch):
	monkeypatch.setattr(ocr_invoice, "read_invoice_file", lambda url: dict(READING, document_type="receipt"))
	review = ocr_invoice.ocr_read_invoice_for_review("/f.jpg", "Purchase Invoice", "SITIAME")
	assert "ne ressemble pas a une facture" in review["warnings"][0]


def test_unsupported_doctype_is_refused(env):
	with pytest.raises(frappe.ValidationError):
		ocr_invoice.ocr_read_invoice_for_review("/f.jpg", "Journal Entry", "SITIAME")


def test_corrections_replace_the_reading_and_become_certain():
	data = {"fields": dict(READING["fields"]), "confidence": dict(READING["confidence"])}
	corrected = ocr_invoice._apply_corrections(
		data,
		{
			"supplier_name": "TRACTAFRIC MOTORS",  # corrected
			"invoice_number": "FA-12",  # unchanged
			"grand_total": "287624",  # corrected, typed as text
			"subtotal": 243749,  # completed
			"tax_amount": 0,  # left empty
			"due_date": "",
		},
	)
	assert corrected == ["supplier_name", "subtotal", "grand_total"]
	assert data["fields"]["grand_total"] == 287624.0
	assert data["confidence"]["grand_total"] == 1.0
	assert data["confidence"]["subtotal"] == 1.0
	assert "tax_amount" not in data["fields"]
	assert "due_date" not in data["fields"]


def test_a_field_cleared_by_the_user_is_removed():
	data = {"fields": {"invoice_number": "FA-12"}, "confidence": {"invoice_number": 0.4}}
	assert ocr_invoice._apply_corrections(data, {"invoice_number": None}) == ["invoice_number"]
	assert data["fields"] == {} and data["confidence"] == {}


def test_fields_not_sent_are_left_as_read():
	data = {"fields": {"invoice_number": "FA-12"}, "confidence": {"invoice_number": 0.4}}
	assert ocr_invoice._apply_corrections(data, {}) == []
	assert data["fields"] == {"invoice_number": "FA-12"}
