# -*- coding: utf-8 -*-
# Copyright (c) 2026, Sitiame Capital
# License: MIT

import requests

import frappe
from frappe import _

# Sandbox (sk_test_ keys) and production (sk_live_ keys) are two different
# API hosts -- same split as CinetPay's official SDK (cinetpay-js,
# src/types/config.ts). A live key sent to the sandbox host is refused.
CINETPAY_SANDBOX_URL = "https://api.cinetpay.net"
CINETPAY_PRODUCTION_URL = "https://api.cinetpay.co"
_TOKEN_CACHE_KEY = "cinetpay_oauth_token"


def get_base_url():
	"""site_config "cinetpay_base_url" wins; otherwise chosen from the key."""
	explicit = frappe.conf.get("cinetpay_base_url")
	if explicit:
		return explicit.rstrip("/")
	api_key = frappe.conf.get("cinetpay_api_key") or ""
	return CINETPAY_PRODUCTION_URL if api_key.startswith("sk_live_") else CINETPAY_SANDBOX_URL


def _token_cache_key():
	# per host, so switching from sandbox to live keys never reuses a
	# sandbox token against production
	return f"{_TOKEN_CACHE_KEY}:{get_base_url()}"


def normalize_phone(phone):
	"""CinetPay needs an international number: a local Ivorian "0143875302"
	makes it open a checkout session that is FAILED at once (transaction id
	"ER-P-...", checkout page 404) -- verified in sandbox on 2026-09-24,
	while "+2250143875302" or no phone at all both work. Returns the
	+225 form, or None when the number can't be made safe (then it is
	simply not sent)."""
	digits = "".join(ch for ch in (phone or "") if ch.isdigit())
	raw = (phone or "").strip()
	if raw.startswith("+") and 8 <= len(digits) <= 15:
		return "+" + digits
	if digits.startswith("00") and 10 <= len(digits) - 2 <= 15:
		return "+" + digits[2:]
	if digits.startswith("225") and len(digits) == 13:
		return "+" + digits
	if len(digits) == 10:
		return "+225" + digits
	return None


def _get_credentials():
	api_key = frappe.conf.get("cinetpay_api_key")
	api_password = frappe.conf.get("cinetpay_api_password")
	if not api_key or not api_password:
		frappe.throw(_("cinetpay_api_key / cinetpay_api_password ne sont pas configures dans site_config.json."))
	return api_key, api_password


def get_access_token():
	cached = frappe.cache().get_value(_token_cache_key())
	if cached:
		return cached

	api_key, api_password = _get_credentials()
	try:
		response = requests.post(
			f"{get_base_url()}/v1/oauth/login",
			json={"api_key": api_key, "api_password": api_password},
			timeout=20,
		)
	except requests.RequestException as e:
		frappe.throw(_("CinetPay injoignable (authentification) : {0}").format(str(e)))

	if response.status_code >= 400:
		frappe.throw(_("Authentification CinetPay refusee : {0}").format(response.text))

	data = response.json()
	token = data.get("access_token")
	if not token:
		frappe.throw(_("Reponse d'authentification CinetPay invalide : {0}").format(data))

	expires_in = int(data.get("expires_in") or 3000)
	# safety margin so a cached token is never handed out right as it expires
	frappe.cache().set_value(_token_cache_key(), token, expires_in_sec=max(expires_in - 60, 60))
	return token


def init_payment(merchant_transaction_id, amount, designation, notify_url, success_url, failed_url, customer=None):
	token = get_access_token()

	client_first_name = "Sitiame"
	client_last_name = "Capital"
	client_email = frappe.conf.get("cinetpay_default_client_email") or "contact@sitiame-capital.com"
	client_phone_number = None

	if customer and isinstance(customer, dict):
		if customer.get("first_name"):
			client_first_name = customer["first_name"]
		if customer.get("last_name"):
			client_last_name = customer["last_name"]
		if customer.get("email"):
			client_email = customer["email"]
		if customer.get("phone"):
			client_phone_number = normalize_phone(customer["phone"])

	payload = {
		"currency": "XOF",
		"merchant_transaction_id": merchant_transaction_id,
		"amount": amount,
		"lang": "fr",
		"designation": designation,
		"client_first_name": client_first_name,
		"client_last_name": client_last_name,
		"client_email": client_email,
		"success_url": success_url,
		"failed_url": failed_url,
		"notify_url": notify_url,
		"direct_pay": False,
	}

	if client_phone_number:
		payload["client_phone_number"] = client_phone_number

	try:
		response = requests.post(
			f"{get_base_url()}/v1/payment",
			json=payload,
			headers={"Authorization": f"Bearer {token}"},
			timeout=30,
		)
	except requests.RequestException as e:
		frappe.throw(_("CinetPay injoignable (initialisation du paiement) : {0}").format(str(e)))

	data = response.json()
	if response.status_code >= 400 or data.get("status") != "OK":
		frappe.throw(_("CinetPay a refuse la demande de paiement : {0}").format(data.get("message") or data))

	return data


def get_payment_status(merchant_transaction_id):
	token = get_access_token()
	try:
		response = requests.get(
			f"{get_base_url()}/v1/payment/{merchant_transaction_id}",
			headers={"Authorization": f"Bearer {token}"},
			timeout=20,
		)
	except requests.RequestException as e:
		frappe.throw(_("CinetPay injoignable (statut du paiement) : {0}").format(str(e)))

	return response.json()
