# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Invoice reading by Mistral OCR, tried before Gemini (vision_invoice.py).

One call to /v1/ocr reads the PDF or photo and fills the same JSON schema
as the Gemini reader (a "document annotation"). API keys live in
site_config.json ("mistral_api_keys", a list), never in this repo: when a
key is exhausted (429) or refused (401/403) it is set aside and the next
one is tried; when none is left the caller moves on to Gemini."""

import base64
import hashlib
import json

import frappe
import requests

API_URL = "https://api.mistral.ai/v1/ocr"
MODEL = "mistral-ocr-latest"
TIMEOUT = 90
CACHE_TTL_SECONDS = 10 * 60
# a key with no quota at all (limit 0, plan not activated) or refused is
# skipped for an hour; one that only hit its per-minute limit, for a minute
KEY_LOCKOUT_SECONDS = 60 * 60
RATE_LOCKOUT_SECONDS = 60
# Mistral OCR does not read HEIC photos: Gemini does
MIME_TYPES = ("application/pdf", "image/jpeg", "image/png", "image/webp")


def _api_keys():
	return [k for k in (frappe.conf.get("mistral_api_keys") or []) if k]


def _lockout_cache_key(api_key):
	return f"mistral:key:exhausted:{hashlib.md5(api_key.encode()).hexdigest()[:12]}"


def _available_keys():
	return [k for k in _api_keys() if not frappe.cache().get_value(_lockout_cache_key(k))]


def _lockout(api_key, seconds):
	frappe.cache().set_value(_lockout_cache_key(api_key), True, expires_in_sec=seconds)


def supports(mime):
	return mime in MIME_TYPES


def annotate(mime, content, prompt, schema, cache_key=None):
	"""Read a document into `schema` (a JSON schema). Returns {"ok": bool,
	"text": the JSON answer, "error": str|None}."""
	if not _api_keys():
		return {"ok": False, "text": "", "error": "Aucune cle MISTRAL configuree."}
	if cache_key:
		cached = frappe.cache().get_value(cache_key)
		if cached is not None:
			return {"ok": True, "text": cached, "error": None}

	data_url = f"data:{mime};base64," + base64.b64encode(content).decode()
	document = (
		{"type": "document_url", "document_url": data_url}
		if mime == "application/pdf"
		else {"type": "image_url", "image_url": data_url}
	)
	payload = {
		"model": MODEL,
		"document": document,
		"document_annotation_format": {"type": "json_schema", "json_schema": {"name": "document", "schema": schema}},
		"document_annotation_prompt": prompt,
	}

	last_error = ""
	for api_key in _available_keys():
		try:
			response = requests.post(
				API_URL, json=payload, headers={"Authorization": f"Bearer {api_key}"}, timeout=TIMEOUT
			)
		except Exception as e:
			last_error = str(e)
			continue  # network trouble: maybe not for the next key's account

		if response.status_code == 200:
			text = _answer(response.json())
			if text is None:
				return {"ok": False, "text": "", "error": "Reponse Mistral sans annotation."}
			if cache_key:
				frappe.cache().set_value(cache_key, text, expires_in_sec=CACHE_TTL_SECONDS)
			return {"ok": True, "text": text, "error": None}

		last_error = _error_message(response)
		if response.status_code == 429:
			no_quota = response.headers.get("x-ratelimit-limit-req-minute") == "0"
			_lockout(api_key, KEY_LOCKOUT_SECONDS if no_quota else RATE_LOCKOUT_SECONDS)
		elif response.status_code in (401, 403):
			_lockout(api_key, KEY_LOCKOUT_SECONDS)
		elif response.status_code < 500:
			break  # the request itself is refused: another key won't change that

	return {"ok": False, "text": "", "error": last_error or "Toutes les cles MISTRAL sont epuisees."}


def _answer(data):
	"""The annotation JSON, its raw_text taken from the OCR pages when the
	model left it empty. None when there is no usable annotation."""
	try:
		answer = json.loads(data.get("document_annotation") or "")
	except (ValueError, TypeError):
		return None
	if not isinstance(answer, dict):
		return None
	if not (answer.get("raw_text") or "").strip():
		answer["raw_text"] = "\n\n".join(page.get("markdown", "") for page in data.get("pages") or [])
	return json.dumps(answer, ensure_ascii=False)


def _error_message(response):
	try:
		return str(response.json().get("message") or f"HTTP {response.status_code}")
	except ValueError:
		return f"HTTP {response.status_code}"
