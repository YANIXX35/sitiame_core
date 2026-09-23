# -*- coding: utf-8 -*-
# Copyright (c) 2026, Sitiame Capital
# License: MIT

import requests

import frappe
from frappe import _

CINETPAY_BASE_URL = "https://api.cinetpay.net"
_TOKEN_CACHE_KEY = "cinetpay_oauth_token"


def _get_credentials():
	api_key = frappe.conf.get("cinetpay_api_key")
	api_password = frappe.conf.get("cinetpay_api_password")
	if not api_key or not api_password:
		frappe.throw(_("cinetpay_api_key / cinetpay_api_password ne sont pas configures dans site_config.json."))
	return api_key, api_password


def get_access_token():
	cached = frappe.cache().get_value(_TOKEN_CACHE_KEY)
	if cached:
		return cached

	api_key, api_password = _get_credentials()
	try:
		response = requests.post(
			f"{CINETPAY_BASE_URL}/v1/oauth/login",
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
	frappe.cache().set_value(_TOKEN_CACHE_KEY, token, expires_in_sec=max(expires_in - 60, 60))
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
			client_phone_number = customer["phone"]

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
			f"{CINETPAY_BASE_URL}/v1/payment",
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
			f"{CINETPAY_BASE_URL}/v1/payment/{merchant_transaction_id}",
			headers={"Authorization": f"Bearer {token}"},
			timeout=20,
		)
	except requests.RequestException as e:
		frappe.throw(_("CinetPay injoignable (statut du paiement) : {0}").format(str(e)))

	return response.json()
