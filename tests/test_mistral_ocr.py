# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Mistral OCR reading (sitiame_core/mistral_ocr.py): key rotation, and
vision_invoice's Mistral -> Gemini order."""

import json

import frappe
import pytest

from sitiame_core import gemini_assistant, mistral_ocr
from sitiame_core import vision_invoice as vision

ANSWER = {
	"document_type": "invoice",
	"fields": {"invoice_number": "FA-1", "supplier_name": "IVOIRE SERVICES", "grand_total": 590000},
	"confidence": {"invoice_number": 0.9},
	"line_items": [{"item_name": "Loyer", "qty": 1, "rate": 500000, "amount": 500000}],
	"image_quality": "good",
	"raw_text": "",
}


class Response:
	def __init__(self, status_code, body, headers=None):
		self.status_code, self._body, self.headers = status_code, body, headers or {}

	def json(self):
		return self._body


class Cache:
	def __init__(self):
		self.values = {}

	def get_value(self, key):
		return self.values.get(key)

	def set_value(self, key, value, expires_in_sec=None):
		self.values[key] = value


@pytest.fixture
def mistral(monkeypatch):
	state = {"responses": [], "keys_used": [], "payloads": [], "cache": Cache()}

	def post(url, json=None, headers=None, timeout=None):
		state["keys_used"].append(headers["Authorization"].removeprefix("Bearer "))
		state["payloads"].append(json)
		return state["responses"].pop(0)

	monkeypatch.setattr(mistral_ocr.requests, "post", post)
	monkeypatch.setattr(frappe, "cache", lambda: state["cache"], raising=False)
	monkeypatch.setattr(frappe, "conf", frappe._dict(mistral_api_keys=["k1", "k2"]), raising=False)
	monkeypatch.setattr(frappe, "logger", lambda *a, **k: frappe._dict(warning=lambda *a: None), raising=False)
	return state


def ok(answer=ANSWER):
	return Response(200, {"document_annotation": json.dumps(answer), "pages": [{"markdown": "IVOIRE SERVICES\nFACTURE FA-1"}]})


def annotate(mime="application/pdf"):
	return mistral_ocr.annotate(mime, b"pdf", "lis", {"type": "object"})


def test_pdf_is_sent_as_a_document_with_the_schema(mistral):
	mistral["responses"] = [ok()]
	result = annotate()
	payload = mistral["payloads"][0]
	assert payload["document"] == {"type": "document_url", "document_url": "data:application/pdf;base64,cGRm"}
	assert payload["document_annotation_format"]["json_schema"]["schema"] == {"type": "object"}
	assert payload["document_annotation_prompt"] == "lis"
	assert result["ok"]


def test_image_is_sent_as_an_image(mistral):
	mistral["responses"] = [ok()]
	annotate("image/jpeg")
	assert mistral["payloads"][0]["document"]["type"] == "image_url"


def test_empty_raw_text_is_taken_from_the_ocr_pages(mistral):
	mistral["responses"] = [ok()]
	assert json.loads(annotate()["text"])["raw_text"] == "IVOIRE SERVICES\nFACTURE FA-1"


def test_exhausted_key_switches_to_the_next_and_is_set_aside(mistral):
	mistral["responses"] = [Response(429, {"message": "Rate limit exceeded"}, {"x-ratelimit-limit-req-minute": "0"}), ok(), ok()]
	assert annotate()["ok"]
	assert mistral["keys_used"] == ["k1", "k2"]
	annotate()  # k1 is not retried while set aside
	assert mistral["keys_used"] == ["k1", "k2", "k2"]


def test_refused_key_switches_to_the_next(mistral):
	mistral["responses"] = [Response(401, {"message": "Unauthorized"}), ok()]
	assert annotate()["ok"]
	assert mistral["keys_used"] == ["k1", "k2"]


def test_all_keys_exhausted_fails(mistral):
	mistral["responses"] = [Response(429, {"message": "Rate limit exceeded"}), Response(429, {"message": "Rate limit exceeded"})]
	result = annotate()
	assert not result["ok"] and result["error"] == "Rate limit exceeded"


def test_a_refused_request_is_not_retried_with_other_keys(mistral):
	mistral["responses"] = [Response(422, {"message": "bad schema"})]
	assert not annotate()["ok"]
	assert mistral["keys_used"] == ["k1"]


def test_no_key_configured(mistral, monkeypatch):
	monkeypatch.setattr(frappe, "conf", frappe._dict(), raising=False)
	assert not annotate()["ok"]
	assert mistral["keys_used"] == []


def test_json_schema_conversion():
	schema = vision.json_schema(vision.RESPONSE_SCHEMA)
	fields = schema["properties"]["fields"]["properties"]
	assert fields["grand_total"] == {"type": ["number", "null"]}
	assert fields["supplier_name"] == {"type": ["string", "null"]}
	assert schema["properties"]["document_type"]["enum"] == list(vision.DOCUMENT_TYPES)
	assert schema["properties"]["line_items"]["items"]["required"] == ["item_name"]
	assert "required" in schema


# -- vision_invoice: Mistral first, Gemini when Mistral can't --


@pytest.fixture
def gemini(monkeypatch, mistral):
	calls = []

	def generate(payload, cache_key=None, timeout=None):
		calls.append(payload)
		return {"ok": True, "text": json.dumps(dict(ANSWER, fields={"invoice_number": "GEMINI"})), "error": None}

	monkeypatch.setattr(gemini_assistant, "_api_keys", lambda: ["g1"])
	monkeypatch.setattr(gemini_assistant, "generate", generate)
	return calls


def test_mistral_reads_first(gemini, mistral):
	mistral["responses"] = [ok()]
	data = vision.read_document("facture.pdf", b"pdf")
	assert data["fields"]["invoice_number"] == "FA-1"
	assert gemini == []


def test_gemini_takes_over_when_mistral_keys_are_exhausted(gemini, mistral):
	mistral["responses"] = [Response(429, {"message": "quota"}), Response(429, {"message": "quota"})]
	data = vision.read_document("facture.pdf", b"pdf")
	assert data["fields"]["invoice_number"] == "GEMINI"


def test_gemini_takes_over_when_mistral_answer_is_unusable(gemini, mistral):
	mistral["responses"] = [Response(200, {"document_annotation": "pas du json"})]
	assert vision.read_document("facture.pdf", b"pdf")["fields"]["invoice_number"] == "GEMINI"


def test_heic_photo_goes_straight_to_gemini(gemini, mistral):
	assert vision.read_document("photo.heic", b"img")["fields"]["invoice_number"] == "GEMINI"
	assert mistral["keys_used"] == []
