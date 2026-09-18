# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""ERPNext port of PME360's GeminiOpsAssistantService.php: same key
rotation (quota 429 -> next key), model fallback, exponential retry and
identical-response caching, using frappe.cache() instead of Laravel's
Cache facade. API keys live in site_config.json ("gemini_api_keys"), never
in this repo -- see set_gemini_config.py (run once via bench console).

Deliberately NOT a port of PME360's 1183-line AdminOpsCenterController
(PME360-specific SLA/alerts/risk context) -- context here is built from
ERPNext data already exposed by this app (see api.py's
build_assistant_context()).
"""

import hashlib
import json
import time

import frappe
import requests

DEFAULT_MODEL = "gemini-2.5-flash"
FALLBACK_MODELS = ["gemini-2.5-flash-lite", "gemini-flash-latest"]
TIMEOUT = 30
MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 1
CACHE_TTL_SECONDS = 10 * 60
KEY_LOCKOUT_SECONDS = 60 * 60
CB_MAX_FAILURES = 5
CB_TIME_WINDOW_SECONDS = 120
CB_LOCKOUT_SECONDS = 300


def _api_keys():
	return [k for k in (frappe.conf.get("gemini_api_keys") or []) if k]


def _key_lockout_cache_key(api_key):
	return f"gemini:key:exhausted:{hashlib.md5(api_key.encode()).hexdigest()[:12]}"


def _available_keys():
	all_keys = _api_keys()
	return [k for k in all_keys if not frappe.cache().get_value(_key_lockout_cache_key(k))]


def _lockout_key(api_key):
	frappe.cache().set_value(_key_lockout_cache_key(api_key), True, expires_in_sec=KEY_LOCKOUT_SECONDS)


def _is_model_locked(model):
	return bool(frappe.cache().get_value(f"gemini:cb:locked:{model}"))


def _register_failure(model):
	failures_key = f"gemini:cb:failures:{model}"
	now = time.time()
	failures = frappe.cache().get_value(failures_key) or []
	failures = [ts for ts in failures if (now - ts) < CB_TIME_WINDOW_SECONDS]
	failures.append(now)
	frappe.cache().set_value(failures_key, failures, expires_in_sec=CB_TIME_WINDOW_SECONDS)

	if len(failures) >= CB_MAX_FAILURES:
		frappe.cache().set_value(f"gemini:cb:locked:{model}", True, expires_in_sec=CB_LOCKOUT_SECONDS)


def chat(messages):
	"""messages: list of {"role": "system"|"user"|"assistant", "content": str}
	Returns {"ok": bool, "answer": str, "error": str|None}."""

	available_keys = _available_keys()
	if not available_keys:
		all_keys = _api_keys()
		if not all_keys:
			return {"ok": False, "answer": "", "error": "Aucune cle GEMINI configuree."}
		for k in all_keys:
			frappe.cache().delete_value(_key_lockout_cache_key(k))
		available_keys = all_keys

	cache_key = "gemini:chat:" + hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
	cached = frappe.cache().get_value(cache_key)
	if cached is not None:
		return {"ok": True, "answer": cached, "error": None}

	contents = []
	system_parts = []
	for msg in messages:
		role = msg.get("role", "user")
		content = (msg.get("content") or "").strip()
		if not content:
			continue
		if role == "system":
			system_parts.append({"text": content})
		else:
			gemini_role = "model" if role in ("assistant", "model") else "user"
			contents.append({"role": gemini_role, "parts": [{"text": content}]})

	payload = {"contents": contents, "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1200}}
	if system_parts:
		payload["systemInstruction"] = {"parts": system_parts}

	models_to_try = list(dict.fromkeys([DEFAULT_MODEL, *FALLBACK_MODELS]))
	last_error = ""

	for model in models_to_try:
		if _is_model_locked(model):
			continue

		for api_key in _available_keys():
			attempts = 0
			while attempts < MAX_ATTEMPTS:
				attempts += 1
				url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

				try:
					response = requests.post(url, json=payload, timeout=TIMEOUT)
					data = response.json() if response.content else {}

					if response.status_code == 200:
						answer = (
							(data.get("candidates") or [{}])[0]
							.get("content", {})
							.get("parts", [{}])[0]
							.get("text", "")
						)
						if answer:
							frappe.cache().set_value(cache_key, answer.strip(), expires_in_sec=CACHE_TTL_SECONDS)
							return {"ok": True, "answer": answer.strip(), "error": None}

					last_error = (data.get("error") or {}).get("message", f"HTTP {response.status_code}")

					if response.status_code == 429:
						_lockout_key(api_key)
						break

					is_transient = response.status_code == 503 or "overloaded" in last_error.lower()
					if is_transient and attempts < MAX_ATTEMPTS:
						time.sleep(BASE_DELAY_SECONDS * (2 ** (attempts - 1)))
					else:
						_register_failure(model)
						break

				except Exception as e:
					last_error = str(e)
					if attempts < MAX_ATTEMPTS:
						time.sleep(BASE_DELAY_SECONDS * (2 ** (attempts - 1)))
					else:
						_register_failure(model)
						break

	return {
		"ok": False,
		"answer": "",
		"error": "Le service de l'assistant IA est momentanement tres sollicite. Veuillez reessayer.",
	}
