# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Subscription paid through Jèko (sitiame_core/jeko_client.py and
subscription_api): requests sent, statuses read, signed webhook."""

import hashlib
import hmac
import json

import frappe
import pytest

from sitiame_core import jeko_client, subscription_api as sa

CONF = frappe._dict(jeko_api_key="key", jeko_api_key_id="key-id", jeko_store_id="store-uuid", jeko_webhook_secret="s3cret")


class Response:
	def __init__(self, status_code, body):
		self.status_code, self._body = status_code, body

	def json(self):
		return self._body


@pytest.fixture
def jeko(monkeypatch):
	state = {"calls": [], "responses": []}

	def request(method, url, json=None, headers=None, timeout=None):
		state["calls"].append({"method": method, "url": url, "json": json, "headers": headers})
		return state["responses"].pop(0)

	monkeypatch.setattr(jeko_client.requests, "request", request)
	monkeypatch.setattr(frappe, "conf", CONF, raising=False)
	return state


# -- jeko_client --


def test_checkout_request_matches_the_jeko_contract(jeko):
	jeko["responses"] = [Response(201, {"id": "pr-1", "redirectUrl": "https://pay.jeko.africa/pr-1"})]
	jeko_client.create_payment_request("SUB-2026-00023", 15000, "wave", "https://s", "https://e")
	call = jeko["calls"][0]
	assert call["url"] == "https://api.jeko.africa/partner_api/payment_requests"
	assert call["headers"]["X-API-KEY"] == "key" and call["headers"]["X-API-KEY-ID"] == "key-id"
	assert call["json"] == {
		"storeId": "store-uuid",
		"amountCents": 1500000,  # 15 000 FCFA in Jèko "cents"
		"currency": "XOF",
		"reference": "SUB-2026-00023",
		"paymentDetails": {"type": "redirect", "data": {"paymentMethod": "wave", "successUrl": "https://s", "errorUrl": "https://e"}},
	}


def test_payment_link_is_single_use(jeko):
	jeko["responses"] = [Response(201, {"id": "pl-1", "link": "https://pay.jeko.africa/l/pl-1"})]
	jeko_client.create_payment_link("Abonnement Sitiame - OOO", 15000)
	body = jeko["calls"][0]["json"]
	assert body["allowMultiplePayments"] is False and body["amountCents"] == 1500000
	assert 10 <= len(body["title"]) <= 255


def test_short_link_title_is_padded_to_jekos_minimum(jeko):
	jeko["responses"] = [Response(201, {"id": "pl-1", "link": "l"})]
	jeko_client.create_payment_link("A - B", 15000)
	assert len(jeko["calls"][0]["json"]["title"]) == 10


class Refused(Exception):
	pass


def _throw(message, exc=None):
	raise Refused(message)


def test_unknown_operator_is_refused_before_calling_jeko(jeko, monkeypatch):
	monkeypatch.setattr(frappe, "throw", _throw, raising=False)
	with pytest.raises(Refused):
		jeko_client.create_payment_request("SUB-1", 15000, "paypal", "s", "e")
	assert jeko["calls"] == []


def test_jeko_validation_errors_are_shown(jeko, monkeypatch):
	monkeypatch.setattr(frappe, "throw", _throw, raising=False)
	jeko["responses"] = [Response(422, {"message": "Validation failed", "extras": {"errors": [{"field": "reference", "message": "too short"}]}})]
	with pytest.raises(Refused, match="reference: too short"):
		jeko_client.create_payment_request("SUB-1", 15000, "wave", "s", "e")


def test_missing_keys_are_reported(jeko, monkeypatch):
	monkeypatch.setattr(frappe, "throw", _throw, raising=False)
	monkeypatch.setattr(frappe, "conf", frappe._dict(), raising=False)
	with pytest.raises(Refused, match="jeko_api_key"):
		jeko_client.get_payment_request("pr-1")


def _sign(body, secret="s3cret"):
	return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_signature_is_hmac_sha256_of_the_raw_body(jeko):
	body = b'{"status":"success"}'
	assert jeko_client.valid_signature(body, _sign(body))
	assert not jeko_client.valid_signature(body, _sign(body, "other"))
	assert not jeko_client.valid_signature(body + b" ", _sign(body))
	assert not jeko_client.valid_signature(body, None)


# -- live status --


def test_checkout_status(jeko):
	jeko["responses"] = [Response(200, {"status": "success"}), Response(200, {"status": "error"}), Response(200, {"status": "pending"})]
	assert [sa._live_status(sa.CHECKOUT, "pr-1") for _ in range(3)] == [sa.PAID, sa.FAILED, sa.PENDING]
	assert jeko["calls"][0]["url"].endswith("/partner_api/payment_requests/pr-1")


def test_a_used_single_use_link_means_paid(jeko):
	jeko["responses"] = [Response(200, {"canReceivePayments": False}), Response(200, {"canReceivePayments": True})]
	assert sa._live_status(sa.LINK, "pl-1") == sa.PAID
	assert sa._live_status(sa.LINK, "pl-1") == sa.PENDING


def test_older_payments_are_no_longer_queried(jeko):
	# payments recorded before Jèko have no provider
	assert sa._live_status(None, "x") == sa.PENDING
	assert sa._live_status("", "x") == sa.PENDING
	assert jeko["calls"] == []


# -- webhook --


@pytest.fixture
def webhook(monkeypatch, jeko):
	state = {"raw": b"", "signature": None, "paid": [], "set": {}, "logged": [], "payments": {}}

	monkeypatch.setattr(frappe, "request", frappe._dict(get_data=lambda: state["raw"]), raising=False)
	monkeypatch.setattr(frappe, "get_request_header", lambda name, default=None: state["signature"], raising=False)
	monkeypatch.setattr(frappe, "response", {}, raising=False)
	monkeypatch.setattr(frappe, "log_error", lambda title=None, message=None: state["logged"].append(title), raising=False)
	monkeypatch.setattr(sa, "_mark_paid", lambda name: state["paid"].append(name))
	monkeypatch.setattr(frappe.db, "commit", lambda: None, raising=False)

	def get_value(doctype, filters, field=None, **kw):
		if isinstance(filters, dict):
			return state["payments"].get((filters["payment_provider"], filters["transaction_id"]))
		return state["set"].get((filters, field), "En attente" if field == "status" else None)

	monkeypatch.setattr(frappe.db, "get_value", get_value, raising=False)
	monkeypatch.setattr(frappe.db, "set_value", lambda dt, name, field, value: state["set"].__setitem__((name, field), value), raising=False)
	return state


def _post(webhook, body, secret="s3cret"):
	webhook["raw"] = json.dumps(body).encode()
	webhook["signature"] = _sign(webhook["raw"], secret)
	return sa.jeko_subscription_webhook()


def test_paid_checkout_activates_the_subscription(webhook):
	webhook["payments"][(sa.CHECKOUT, "pr-1")] = "SUB-2026-00023"
	result = _post(webhook, {"status": "success", "paymentMethod": "wave", "transactionDetails": {"id": "pr-1", "reference": "SUB-2026-00023"}})
	assert result == {"status": "ok"} and webhook["paid"] == ["SUB-2026-00023"]
	assert webhook["set"][("SUB-2026-00023", "payment_method")] == "wave"


def test_paid_staff_link_activates_the_subscription(webhook):
	webhook["payments"][(sa.LINK, "pl-9")] = "SUB-2026-00024"
	_post(webhook, {"status": "success", "paymentMethod": "orange", "transactionDetails": {"paymentLinkId": "pl-9"}})
	assert webhook["paid"] == ["SUB-2026-00024"]


def test_bad_signature_is_refused_and_nothing_is_paid(webhook):
	webhook["payments"][(sa.CHECKOUT, "pr-1")] = "SUB-2026-00023"
	result = _post(webhook, {"status": "success", "transactionDetails": {"id": "pr-1"}}, secret="forged")
	assert result == {"status": "forbidden"} and frappe.response["http_status_code"] == 401
	assert webhook["paid"] == [] and webhook["logged"] == ["Jèko webhook: signature invalide"]


def test_other_stores_transactions_are_acknowledged_and_ignored(webhook):
	"""The notifymail business shares the account: its transactions are not ours."""
	assert _post(webhook, {"status": "success", "transactionDetails": {"id": "someone-else", "reference": "NM-1"}}) == {"status": "ignored"}
	assert webhook["paid"] == []


def test_reference_must_match_the_document(webhook):
	webhook["payments"][(sa.CHECKOUT, "pr-1")] = "SUB-2026-00023"
	assert _post(webhook, {"status": "success", "transactionDetails": {"id": "pr-1", "reference": "SUB-2026-99999"}}) == {"status": "ignored"}


def test_failed_payment_is_marked_failed(webhook):
	webhook["payments"][(sa.CHECKOUT, "pr-1")] = "SUB-2026-00023"
	_post(webhook, {"status": "error", "transactionDetails": {"id": "pr-1"}})
	assert webhook["set"][("SUB-2026-00023", "status")] == "Échoué" and webhook["paid"] == []


# -- price --


def test_price_defaults_to_15000_and_site_config_overrides_it(monkeypatch):
	monkeypatch.setattr(frappe, "conf", frappe._dict(), raising=False)
	assert sa.subscription_amount() == 15000
	monkeypatch.setattr(frappe, "conf", frappe._dict(sitiame_subscription_amount="20"), raising=False)
	assert sa.subscription_amount() == 20


def test_link_below_jekos_minimum_is_refused_clearly(jeko, monkeypatch):
	monkeypatch.setattr(frappe, "throw", _throw, raising=False)
	with pytest.raises(Refused, match="au moins 100 FCFA"):
		jeko_client.create_payment_link("Abonnement Sitiame - OOO", 20)
	assert jeko["calls"] == []
