# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Jèko Partner API (https://api.jeko.africa), for the Sitiame subscription.

Two products are used:
- Checkout ("payment request", type redirect): the PME picks its operator
  on our Abonnement page, pays in its app and comes back to our page. Status
  read with GET /partner_api/payment_requests/{id}.
- Payment link, single use: the link Sitiame staff send to a PME (WhatsApp,
  e-mail); the payer picks the operator on Jèko's page. Once paid, the link
  answers canReceivePayments = false.

Jèko has NO sandbox: every payment is real. Keys live in site_config.json
only: jeko_api_key, jeko_api_key_id, jeko_store_id (the "Sitiame" store)
and jeko_webhook_secret (that store's webhook)."""

import hashlib
import hmac

import frappe
import requests
from frappe import _

BASE_URL = "https://api.jeko.africa"
TIMEOUT = 20
PAYMENT_METHODS = ("wave", "orange", "mtn", "moov", "djamo")


def _base_url():
	return (frappe.conf.get("jeko_base_url") or BASE_URL).rstrip("/")


def _headers():
	api_key = frappe.conf.get("jeko_api_key")
	api_key_id = frappe.conf.get("jeko_api_key_id")
	if not api_key or not api_key_id:
		frappe.throw(_("jeko_api_key / jeko_api_key_id ne sont pas configures dans site_config.json."))
	return {"X-API-KEY": api_key, "X-API-KEY-ID": api_key_id, "Content-Type": "application/json"}


def _store_id():
	store_id = frappe.conf.get("jeko_store_id")
	if not store_id:
		frappe.throw(_("jeko_store_id n'est pas configure dans site_config.json."))
	return store_id


def amount_cents(amount_xof):
	"""Jèko counts XOF in "cents": 15 000 FCFA is 1 500 000."""
	return int(round(float(amount_xof))) * 100


def _call(method, path, what, json=None):
	try:
		response = requests.request(method, f"{_base_url()}{path}", json=json, headers=_headers(), timeout=TIMEOUT)
	except requests.RequestException as e:
		frappe.throw(_("Jèko injoignable ({0}) : {1}").format(what, str(e)))
	try:
		data = response.json()
	except ValueError:
		data = {}
	if response.status_code >= 400:
		frappe.throw(_("Jèko a refuse la demande ({0}) : {1}").format(what, _error_message(data, response)))
	return data


def _error_message(data, response):
	errors = ((data.get("extras") or {}) if isinstance(data.get("extras"), dict) else {}).get("errors") or []
	details = "; ".join(f"{e.get('field')}: {e.get('message')}" for e in errors if isinstance(e, dict))
	return " - ".join(part for part in (data.get("message"), details) if part) or f"HTTP {response.status_code}"


def create_payment_request(reference, amount_xof, payment_method, success_url, error_url):
	if payment_method not in PAYMENT_METHODS:
		frappe.throw(_("Moyen de paiement inconnu : {0}").format(payment_method))
	return _call(
		"POST",
		"/partner_api/payment_requests",
		_("creation du paiement"),
		json={
			"storeId": _store_id(),
			"amountCents": amount_cents(amount_xof),
			"currency": "XOF",
			"reference": reference,
			"paymentDetails": {
				"type": "redirect",
				"data": {"paymentMethod": payment_method, "successUrl": success_url, "errorUrl": error_url},
			},
		},
	)


def get_payment_request(payment_request_id):
	return _call("GET", f"/partner_api/payment_requests/{payment_request_id}", _("statut du paiement"))


# Jèko refuses payment links below this amount (checkouts accept 1 XOF).
LINK_MIN_XOF = 100


def create_payment_link(title, amount_xof):
	if amount_xof < LINK_MIN_XOF:
		frappe.throw(
			_("Jèko exige au moins {0} FCFA pour un lien de paiement (montant actuel : {1} FCFA). Payez depuis la page Abonnement de la PME.").format(LINK_MIN_XOF, amount_xof)
		)
	return _call(
		"POST",
		"/partner_api/payment_links",
		_("creation du lien de paiement"),
		json={
			"storeId": _store_id(),
			# Jèko requires 10 to 255 characters
			"title": title[:255].ljust(10),
			"amountCents": amount_cents(amount_xof),
			"currency": "XOF",
			"allowMultiplePayments": False,
		},
	)


def get_payment_link(payment_link_id):
	return _call("GET", f"/partner_api/payment_links/{payment_link_id}", _("statut du lien de paiement"))


def valid_signature(raw_body, signature):
	"""Jeko-Signature = HMAC-SHA256 of the raw body with the webhook secret,
	lowercase hex, nothing else."""
	secret = frappe.conf.get("jeko_webhook_secret")
	if not secret or not signature or raw_body is None:
		return False
	if isinstance(raw_body, str):
		raw_body = raw_body.encode()
	expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
	return hmac.compare_digest(expected, signature.strip().lower())
