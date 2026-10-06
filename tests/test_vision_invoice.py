# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Vision reading (Gemini) of invoices, and read_invoice_file's
vision-first / OCR.space-fallback order."""

import json

import frappe
import pytest

from sitiame_core import api
from sitiame_core import gemini_assistant
from sitiame_core import vision_invoice as vision

ANSWER = {
	"document_type": "invoice",
	"fields": {
		"invoice_number": "FA7354176",
		"invoice_date": "2026-09-27",
		"due_date": None,
		"supplier_name": "TRACTAFRIC MOTORS",
		"customer_name": "SITIAME CAPITAL",
		"tax_id": "CI-ABJ-2019",
		"subtotal": 229413,
		"tax_amount": "41 295",
		"grand_total": 270708.0,
	},
	"confidence": {"invoice_number": 0.95, "supplier_name": 0.6, "grand_total": 1.4},
	"line_items": [
		{"item_name": "Filtre a huile", "qty": 2, "rate": 15000, "amount": 30000},
		{"item_name": "Vidange", "qty": None, "rate": None, "amount": 199413},
		{"item_name": "  "},
	],
	"raw_text": "TRACTAFRIC MOTORS\nFACTURE FA7354176\n",
}


def test_normalize_keeps_only_readable_fields():
	data = vision.normalize(ANSWER)
	assert data["fields"] == {
		"invoice_number": "FA7354176",
		"invoice_date": "2026-09-27",
		"supplier_name": "TRACTAFRIC MOTORS",
		"customer_name": "SITIAME CAPITAL",
		"tax_id": "CI-ABJ-2019",
		"subtotal": 229413.0,
		"tax_amount": 41295.0,
		"grand_total": 270708.0,
	}
	assert "due_date" not in data["confidence"]


def test_confidence_is_clamped_and_defaults_to_half():
	confidence = vision.normalize(ANSWER)["confidence"]
	assert confidence["invoice_number"] == 0.95
	assert confidence["grand_total"] == 1.0
	assert confidence["invoice_date"] == 0.5  # not given by the model


def test_line_items_match_the_regex_extraction_shape():
	assert vision.normalize(ANSWER)["line_items"] == [
		{"item_name": "Filtre a huile", "qty": 2.0, "rate": 15000.0},
		{"item_name": "Vidange", "rate": 199413.0, "qty": 1},
	]


def test_consistent_amounts_give_no_warning():
	data = vision.normalize(dict(ANSWER, image_quality="good", amount_in_words_value=270708))
	assert data["warnings"] == []
	assert data["confidence"]["grand_total"] == 1.0


def test_amounts_that_dont_add_up_are_flagged_and_downgraded():
	# real case: a very blurry photo read at 0.7-0.9 with invented totals
	fields = dict(ANSWER["fields"], subtotal=366250, tax_amount=76675, grand_total=397925)
	data = vision.normalize(dict(ANSWER, fields=fields, confidence={"subtotal": 0.8, "tax_amount": 0.7, "grand_total": 0.8}))
	assert "ne font pas le TTC" in data["warnings"][0]
	assert all(data["confidence"][key] == vision.DOUBTFUL_CONFIDENCE for key in ("subtotal", "tax_amount", "grand_total"))
	assert data["confidence"]["invoice_number"] == 0.5  # untouched


def test_a_ten_franc_misread_of_the_total_is_caught():
	# real case: 287 624 read as 287 634 on a blurry photo
	fields = dict(ANSWER["fields"], subtotal=243749, tax_amount=43875, grand_total=287634)
	data = vision.normalize(dict(ANSWER, fields=fields))
	assert "ne font pas le TTC" in data["warnings"][0]


def test_self_consistent_amounts_at_an_impossible_vat_rate_are_flagged():
	# real case: invented 200 788 + 40 878 = 241 666, i.e. 20.36% VAT
	fields = dict(ANSWER["fields"], subtotal=200788, tax_amount=40878, grand_total=241666)
	data = vision.normalize(dict(ANSWER, fields=fields))
	assert len(data["warnings"]) == 1
	assert "20.36%" in data["warnings"][0]
	assert data["confidence"]["grand_total"] == vision.DOUBTFUL_CONFIDENCE


@pytest.mark.parametrize("subtotal, tax", [(243749, 43875), (100000, 9000), (100000, 19000), (182499, 32850)])
def test_real_vat_rates_are_accepted(subtotal, tax):
	fields = dict(ANSWER["fields"], subtotal=subtotal, tax_amount=tax, grand_total=subtotal + tax)
	assert vision.normalize(dict(ANSWER, fields=fields))["warnings"] == []


def test_total_contradicting_the_amount_in_words_is_flagged():
	data = vision.normalize(dict(ANSWER, amount_in_words_value=287624))
	assert "en lettres" in data["warnings"][0]
	assert data["confidence"]["grand_total"] == vision.DOUBTFUL_CONFIDENCE


def test_missing_total_is_taken_from_the_amount_in_words():
	fields = dict(ANSWER["fields"], grand_total=None, subtotal=None, tax_amount=None)
	data = vision.normalize(dict(ANSWER, fields=fields, amount_in_words_value=287624))
	assert data["fields"]["grand_total"] == 287624.0
	assert data["confidence"]["grand_total"] == 0.6
	assert len(data["warnings"]) == 1


def test_poor_photo_is_flagged_and_nothing_shown_as_sure():
	data = vision.normalize(dict(ANSWER, image_quality="poor"))
	assert "reprenez la photo" in data["warnings"][0]
	assert max(data["confidence"].values()) == vision.POOR_PHOTO_CONFIDENCE


@pytest.mark.parametrize("value", ["27/09/2026", "2026-13-45", "hier"])
def test_bad_dates_are_dropped(value):
	answer = dict(ANSWER, fields=dict(ANSWER["fields"], invoice_date=value))
	assert "invoice_date" not in vision.normalize(answer)["fields"]


def test_unknown_document_type_becomes_unknown():
	assert vision.normalize(dict(ANSWER, document_type="menu"))["document_type"] == "unknown"


@pytest.mark.parametrize(
	"filename, mime",
	[("scan.JPG", "image/jpeg"), ("f.pdf", "application/pdf"), ("a.heic", "image/heic"), ("x.docx", None), ("noext", None)],
)
def test_mime_type(filename, mime):
	assert vision.mime_type(filename) == mime


class Calls(list):
	result = None


@pytest.fixture
def gemini(monkeypatch):
	calls = Calls()

	def generate(payload, cache_key=None, timeout=None, models=None):
		calls.append(payload)
		return calls.result

	calls.result = {"ok": True, "text": json.dumps(ANSWER), "error": None}
	monkeypatch.setattr(gemini_assistant, "_api_keys", lambda: ["key"])
	monkeypatch.setattr(gemini_assistant, "generate", generate)
	monkeypatch.setattr(frappe, "logger", lambda *a, **k: frappe._dict(warning=lambda *a: None), raising=False)
	return calls


def test_read_document_sends_the_image_and_a_json_schema(gemini):
	vision.read_document("scan.jpg", b"img")
	(payload,) = gemini
	inline = payload["contents"][0]["parts"][0]["inline_data"]
	assert inline == {"mime_type": "image/jpeg", "data": "aW1n"}
	assert payload["generationConfig"]["responseMimeType"] == "application/json"


def test_read_document_returns_none_when_gemini_fails(gemini):
	gemini.result = {"ok": False, "text": "", "error": "quota"}
	assert vision.read_document("scan.jpg", b"img") is None


def test_read_document_returns_none_on_invalid_json(gemini):
	gemini.result = {"ok": True, "text": "pas du json", "error": None}
	assert vision.read_document("scan.jpg", b"img") is None
	assert len(gemini) == len(vision.GEMINI_MODELS)  # every model was given its chance


def test_a_cut_off_answer_moves_on_to_the_next_model(gemini, monkeypatch):
	answers = [{"ok": True, "text": '{"document_type": "inv', "error": None}, {"ok": True, "text": json.dumps(ANSWER), "error": None}]
	tried = []

	def generate(payload, cache_key=None, timeout=None, models=None):
		tried.append(models)
		return answers.pop(0)

	monkeypatch.setattr(gemini_assistant, "generate", generate)
	assert vision.read_document("scan.jpg", b"img")["fields"]["invoice_number"] == "FA7354176"
	assert tried == [[vision.GEMINI_MODELS[0]], [vision.GEMINI_MODELS[1]]]


def test_unsupported_file_skips_gemini(gemini):
	assert vision.read_document("facture.docx", b"doc") is None
	assert gemini == []


def test_no_key_skips_gemini(gemini, monkeypatch):
	monkeypatch.setattr(gemini_assistant, "_api_keys", lambda: [])
	assert vision.read_document("scan.jpg", b"img") is None
	assert gemini == []


# -- read_invoice_file: vision first, OCR.space as fallback / complement --

OCR = {
	"text": "Fournisseur : TRACTAFRIC\nTOTAL TTC 270 708",
	"document_type": "invoice",
	"fields": {"supplier_name": "TRACTAFRIC", "grand_total": 270708.0, "invoice_number": "OCR-1"},
	"confidence": {"supplier_name": 0.9, "grand_total": 0.9, "invoice_number": 0.9},
	"line_items": [{"item_name": "ligne OCR", "qty": 1, "rate": 5.0}],
}


@pytest.fixture
def reading(monkeypatch):
	state = {"vision": None, "ocr_calls": 0}

	def ocr(filename, content):
		state["ocr_calls"] += 1
		return json.loads(json.dumps(OCR))

	monkeypatch.setattr(api, "get_readable_file", lambda url: frappe._dict(file_url=url))
	monkeypatch.setattr(frappe.utils, "file_manager", frappe._dict(get_file=lambda url: ("scan.jpg", b"img")), raising=False)
	monkeypatch.setattr(vision, "read_document", lambda filename, content: state["vision"])
	monkeypatch.setattr(api, "_read_with_ocr_space", ocr)
	monkeypatch.setattr(frappe, "logger", lambda *a, **k: frappe._dict(info=lambda *a: None), raising=False)
	return state


def test_complete_vision_reading_does_not_call_ocr(reading):
	reading["vision"] = vision.normalize(ANSWER)
	data = api.read_invoice_file("/private/files/scan.jpg")
	assert data["source"] == "vision"
	assert reading["ocr_calls"] == 0
	assert data["fields"]["invoice_number"] == "FA7354176"
	assert data["amount"] == 270708.0
	assert data["text"].startswith("TRACTAFRIC")


def test_vision_unavailable_falls_back_to_ocr(reading):
	data = api.read_invoice_file("/private/files/scan.jpg")
	assert data["source"] == "ocr"
	assert data["fields"]["invoice_number"] == "OCR-1"


def test_ocr_fills_only_the_key_fields_vision_missed(reading):
	answer = dict(ANSWER, fields=dict(ANSWER["fields"], supplier_name=None, customer_name=None))
	reading["vision"] = vision.normalize(answer)
	data = api.read_invoice_file("/private/files/scan.jpg")
	assert data["source"] == "vision+ocr"
	assert data["fields"]["supplier_name"] == "TRACTAFRIC"
	assert data["confidence"]["supplier_name"] == 0.9
	# what vision did read is kept
	assert data["fields"]["invoice_number"] == "FA7354176"
	assert data["line_items"][0]["item_name"] == "Filtre a huile"


def test_ocr_failure_while_completing_keeps_the_vision_reading(reading, monkeypatch):
	def broken(filename, content):
		raise frappe.ValidationError("OCR down")

	monkeypatch.setattr(api, "_read_with_ocr_space", broken)
	answer = dict(ANSWER, fields=dict(ANSWER["fields"], grand_total=None, subtotal=None))
	reading["vision"] = vision.normalize(answer)
	data = api.read_invoice_file("/private/files/scan.jpg")
	assert data["source"] == "vision"
	assert "grand_total" not in data["fields"]
