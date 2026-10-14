# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""The four PME360 offers paid through Jèko (subscription_api): the price is
the catalogue's, never the browser's; the offer is applied to the company
only once Jèko confirms a payment of the expected amount, once."""

import datetime
import inspect
import json
import sys
import types

import frappe
import pytest

from sitiame_core import jeko_client, subscription_api as sa

CONF = frappe._dict(jeko_api_key="key", jeko_api_key_id="key-id", jeko_store_id="store-uuid", jeko_webhook_secret="s3cret")


class Refused(Exception):
	pass


def _throw(message, exc=None):
	raise Refused(message)


def _paid(amount, currency="XOF", fees=0):
	return {"amount": {"amount": amount, "currency": currency}, "fees": {"amount": fees, "currency": currency}}


# -- catalogue --


@pytest.mark.parametrize(
	"offer, expected",
	[("Essentiel", 25_000), ("Conformite", 45_000), ("Pilotage", 100_000), ("Transformation", 250_000)],
)
def test_the_four_offers_at_the_default_regime(offer, expected):
	"""The amounts of the Offres PME360 page, for a PME whose tax regime is
	not filled in yet (every PME on 2026-10-14)."""
	assert sa.offer_price(offer, None) == expected
	assert sa.offer_price(offer, "") == expected
	assert sa.offer_price(offer, "RME") == expected


@pytest.mark.parametrize(
	"regime, expected",
	[
		("TEE", [15_000, 30_000, 75_000, 200_000]),
		("RME", [25_000, 45_000, 100_000, 250_000]),
		("RSI", [50_000, 85_000, 175_000, 300_000]),
		("RNI", [80_000, 130_000, 250_000, 400_000]),
	],
)
def test_prices_by_regime_match_the_offres_page(regime, expected):
	offers = ("Essentiel", "Conformite", "Pilotage", "Transformation")
	assert [sa.offer_price(o, regime) for o in offers] == expected


def test_unknown_offer_is_refused(monkeypatch):
	monkeypatch.setattr(frappe, "throw", _throw, raising=False)
	for offer in ("Gratuit", "essentiel", "", None):
		with pytest.raises(Refused):
			sa.check_offer(offer)


def test_withdrawn_offer_is_refused(monkeypatch):
	monkeypatch.setattr(frappe, "throw", _throw, raising=False)
	monkeypatch.setitem(sa.PME360_CATALOG, "Pilotage", {**sa.PME360_CATALOG["Pilotage"], "active": False})
	with pytest.raises(Refused, match="n'est plus proposée"):
		sa.check_offer("Pilotage")
	assert "Pilotage" not in [o["key"] for o in sa.offer_catalog()]


def test_catalogue_sent_to_the_pages_is_priced_at_the_regime():
	offers = {o["key"]: o for o in sa.offer_catalog("RSI")}
	assert offers["Conformite"]["price"] == 85_000 and offers["Conformite"]["currency"] == "XOF"
	assert offers["Pilotage"]["features"] and offers["Pilotage"]["label"] == "PME360 Pilotage"


def test_no_universal_15000_left_in_the_payment_flow():
	"""Only the TEE column of Essentiel may still cost 15 000."""
	fifteen = [(k, r) for k, e in sa.PME360_CATALOG.items() for r, p in e["prices"].items() if p == 15_000]
	assert fifteen == [("Essentiel", "TEE")]


# -- creating a payment --


@pytest.fixture
def creating(monkeypatch):
	state = {"company": {"offer": "Essentiel", "regime": ""}, "inserted": [], "company_writes": [], "jeko": []}
	monkeypatch.setattr(frappe, "throw", _throw, raising=False)
	monkeypatch.setattr(frappe, "conf", CONF, raising=False)
	monkeypatch.setattr(frappe, "session", frappe._dict(user="pme@binks.ci"), raising=False)
	monkeypatch.setattr(sa, "_company_offer_and_regime", lambda company: (state["company"]["offer"], state["company"]["regime"]))
	monkeypatch.setattr(sa, "get_user_company", lambda user=None: "binks")
	monkeypatch.setattr(frappe, "get_all", lambda *a, **k: [], raising=False)
	monkeypatch.setattr(frappe.db, "set_value", lambda *a, **k: state["company_writes"].append(a), raising=False)
	monkeypatch.setattr(frappe.db, "commit", lambda: None, raising=False)
	monkeypatch.setattr(frappe.utils, "get_url", lambda: "https://erp", raising=False)

	class Doc(frappe._dict):
		def insert(self, ignore_permissions=False):
			self.name = f"SUB-2026-{len(state['inserted']) + 1:05d}"
			state["inserted"].append(self)
			return self

	monkeypatch.setattr(frappe, "get_doc", lambda data: Doc(data, flags=frappe._dict()), raising=False)

	def save_payment(doc, provider, transaction_id, payment_url, payment_method=None):
		doc.transaction_id, doc.payment_url = transaction_id, payment_url

	monkeypatch.setattr(sa, "_save_payment", save_payment)

	def create_payment_request(reference, amount_xof, payment_method, success_url, error_url):
		state["jeko"].append({"reference": reference, "amountCents": jeko_client.amount_cents(amount_xof)})
		return {"id": "pr-1", "redirectUrl": "https://pay.jeko.africa/pr-1"}

	monkeypatch.setattr(sa.jeko_client, "create_payment_request", create_payment_request)
	return state


@pytest.mark.parametrize(
	"offer, amount",
	[("Essentiel", 25_000), ("Conformite", 45_000), ("Pilotage", 100_000), ("Transformation", 250_000)],
)
def test_checkout_charges_the_chosen_offer(creating, offer, amount):
	result = sa.get_or_create_pme_checkout_url(payment_method="wave", offer=offer)
	payment = creating["inserted"][0]
	# computed on the server, recorded on the payment, sent to Jèko
	assert (payment.offer, payment.amount, payment.currency) == (offer, amount, "XOF")
	assert payment.regime == "RME" and payment.duration_months == 1 and payment.status == sa.PENDING
	assert creating["jeko"][0]["amountCents"] == amount * 100
	assert creating["jeko"][0]["reference"].startswith(payment.name + "-")
	assert result["payment_url"] == "https://pay.jeko.africa/pr-1"


def test_regime_of_the_pme_sets_the_price(creating):
	creating["company"]["regime"] = "RSI"
	sa.get_or_create_pme_checkout_url(payment_method="orange", offer="Conformite")
	assert creating["inserted"][0].amount == 85_000 and creating["jeko"][0]["amountCents"] == 8_500_000


def test_no_offer_sent_charges_the_current_offer(creating):
	creating["company"]["offer"] = "Pilotage"
	sa.get_or_create_pme_checkout_url(payment_method="wave")
	assert (creating["inserted"][0].offer, creating["inserted"][0].amount) == ("Pilotage", 100_000)


def test_the_browser_cannot_send_a_price():
	"""Frappe drops request arguments the method does not declare."""
	params = inspect.signature(sa.get_or_create_pme_checkout_url).parameters
	assert not {"amount", "price", "montant"} & set(params)
	assert not {"amount", "price", "montant"} & set(inspect.signature(sa.create_company_payment_link).parameters)


def test_unknown_offer_creates_no_payment(creating):
	with pytest.raises(Refused, match="Offre inconnue"):
		sa.get_or_create_pme_checkout_url(payment_method="wave", offer="Platine")
	assert creating["inserted"] == [] and creating["jeko"] == []


def test_choosing_an_offer_does_not_change_the_company_before_payment(creating):
	"""Before 2026-10-14 the chosen offer was written on the Company at once:
	an unpaid upgrade still unlocked the higher offer's menus."""
	sa.get_or_create_pme_checkout_url(payment_method="wave", offer="Transformation")
	assert creating["company_writes"] == []


def test_a_pme_always_pays_for_its_own_company(creating):
	sa.get_or_create_pme_checkout_url(payment_method="wave", offer="Pilotage", company="OOO")
	assert creating["inserted"][0].company == "binks"


def test_staff_link_carries_the_offer_and_its_price(creating, monkeypatch):
	monkeypatch.setattr(sa, "_only_staff", lambda: None)
	monkeypatch.setattr(sa.portfolio, "check_company", lambda company, user=None: None)
	monkeypatch.setattr(frappe.db, "exists", lambda *a, **k: True, raising=False)
	links = []
	monkeypatch.setattr(sa.jeko_client, "create_payment_link", lambda title, amount: links.append((title, amount)) or {"id": "pl-1", "link": "https://pay/l"})
	result = sa.create_company_payment_link("ALI SARL", offer="Conformite")
	assert links == [("PME360 Conformité - ALI SARL", 45_000)]
	assert (result["offer"], result["amount"]) == ("Conformite", 45_000)


# -- checking what Jèko says was paid --


@pytest.mark.parametrize(
	"paid, ok",
	[
		(_paid(45_000), True),  # in FCFA
		(_paid(4_500_000), True),  # in Jèko "cents"
		(_paid(44_550, fees=450), True),  # net of fees
		(_paid(25_000), False),  # an Essentiel price for a Conformité payment
		(_paid(45_000, currency="EUR"), False),
		(_paid(""), False),
		({"amount": None}, False),
		(None, False),
		(_paid("abc"), False),
	],
)
def test_amount_paid_must_be_the_expected_one(paid, ok):
	doc = frappe._dict(amount=45_000, currency="XOF")
	assert (sa._amount_mismatch(doc, paid) is None) is ok


def test_legacy_payments_without_currency_are_checked_in_xof():
	assert sa._amount_mismatch(frappe._dict(amount=15_000), _paid(15_000)) is None


# -- activation --


@pytest.fixture
def ledger(monkeypatch):
	"""Subscription Payment and Company rows, as _mark_paid reads them."""
	today = datetime.date(2026, 10, 14)
	state = {
		"payments": {},
		"company": {"binks": {"sitiame_offer": "Essentiel", "sitiame_subscription_ends_on": None}},
		"users": {"pme@binks.ci": ["PME Client"], "compta@binks.ci": ["PME Client"], "staff@sitiame.ci": ["System Manager"]},
		"offer_roles": [],
		"logged": [],
	}

	class Payment(frappe._dict):
		def db_set(self, field, value):
			self[field] = value

	def get_value(doctype, name, field=None, **kwargs):
		if doctype == "Subscription Payment":
			return state["payments"][name].get(field)
		return None

	def set_value(doctype, name, field, value=None):
		row = state["payments"][name] if doctype == "Subscription Payment" else state["company"][name]
		row.update(field if isinstance(field, dict) else {field: value})

	def get_all(doctype, filters=None, pluck=None, **kwargs):
		if doctype == "User Permission":
			return ["pme@binks.ci", "compta@binks.ci", "staff@sitiame.ci"]
		return []

	monkeypatch.setattr(frappe.db, "get_value", get_value, raising=False)
	monkeypatch.setattr(frappe.db, "set_value", set_value, raising=False)
	monkeypatch.setattr(frappe.db, "commit", lambda: None, raising=False)
	monkeypatch.setattr(frappe, "get_doc", lambda doctype, name: state["payments"][name], raising=False)
	monkeypatch.setattr(frappe, "get_all", get_all, raising=False)
	monkeypatch.setattr(frappe, "get_roles", lambda user=None: state["users"].get(user, []), raising=False)
	monkeypatch.setattr(frappe, "log_error", lambda title=None, message=None: state["logged"].append(title), raising=False)
	monkeypatch.setattr(frappe.utils, "now", lambda: "2026-10-14 10:00:00", raising=False)
	monkeypatch.setattr(sa, "today", lambda: today.isoformat())
	monkeypatch.setattr(sa, "add_months", lambda date, months: datetime.date(date.year, date.month + months, date.day))
	monkeypatch.setattr(sa, "_restore_trial_roles", lambda company: None)

	def subscription(company):
		ends = state["company"][company]["sitiame_subscription_ends_on"]
		return {"ends_on": str(ends) if ends else None, "trial_ends_on": None}

	monkeypatch.setattr(sa, "get_company_subscription", subscription)

	setup = types.ModuleType("sitiame_core.setup")
	setup.PME360_OFFER_FIELD = "sitiame_offer"
	monkeypatch.setitem(sys.modules, "sitiame_core.setup", setup)
	roles = types.ModuleType("sitiame_core.offer_roles")
	roles.sync_offer_role = lambda user, offer: state["offer_roles"].append((user, offer))
	monkeypatch.setitem(sys.modules, "sitiame_core.offer_roles", roles)

	def add(name, offer="Conformite", amount=45_000, status=sa.PENDING):
		state["payments"][name] = Payment(
			name=name, company="binks", offer=offer, amount=amount, currency="XOF", duration_months=1, status=status
		)

	state["add"] = add
	return state


def test_confirmed_payment_activates_the_offer_it_paid_for(ledger):
	ledger["add"]("SUB-1")
	assert sa._mark_paid("SUB-1", _paid(45_000)) is True
	payment = ledger["payments"]["SUB-1"]
	assert payment.status == sa.PAID and payment.paid_at
	assert (payment.period_start, payment.period_end) == (datetime.date(2026, 10, 14), datetime.date(2026, 11, 14))
	assert ledger["company"]["binks"]["sitiame_offer"] == "Conformite"
	assert ledger["company"]["binks"]["sitiame_subscription_ends_on"] == datetime.date(2026, 11, 14)
	# every account of the PME gets the offer role, never the staff
	assert ledger["offer_roles"] == [("pme@binks.ci", "Conformite"), ("compta@binks.ci", "Conformite")]


def test_wrong_amount_activates_nothing(ledger):
	ledger["add"]("SUB-1")
	assert sa._mark_paid("SUB-1", _paid(25_000)) is False
	payment = ledger["payments"]["SUB-1"]
	assert payment.status == sa.TO_CHECK and "attendu 45000" in payment.verification_note
	assert ledger["company"]["binks"] == {"sitiame_offer": "Essentiel", "sitiame_subscription_ends_on": None}
	assert ledger["offer_roles"] == [] and ledger["logged"] == ["Jèko : paiement à vérifier"]


def test_a_payment_is_activated_only_once(ledger):
	ledger["add"]("SUB-1")
	sa._mark_paid("SUB-1", _paid(45_000))
	sa._mark_paid("SUB-1", _paid(45_000))
	assert ledger["company"]["binks"]["sitiame_subscription_ends_on"] == datetime.date(2026, 11, 14)
	assert len(ledger["offer_roles"]) == 2


def test_legacy_payment_without_offer_keeps_the_company_offer(ledger):
	ledger["add"]("SUB-OLD", offer=None, amount=15_000)
	assert sa._mark_paid("SUB-OLD", _paid(15_000)) is True
	assert ledger["company"]["binks"]["sitiame_offer"] == "Essentiel" and ledger["offer_roles"] == []


def test_paying_an_active_subscription_stacks_the_month(ledger):
	ledger["company"]["binks"]["sitiame_subscription_ends_on"] = datetime.date(2026, 10, 30)
	ledger["add"]("SUB-1", offer="Pilotage", amount=100_000)
	sa._mark_paid("SUB-1", _paid(10_000_000))
	assert ledger["company"]["binks"]["sitiame_subscription_ends_on"] == datetime.date(2026, 11, 30)


def test_a_failed_renewal_never_touches_the_running_subscription(ledger, monkeypatch):
	ledger["company"]["binks"]["sitiame_subscription_ends_on"] = datetime.date(2026, 10, 30)
	ledger["add"]("SUB-1")
	monkeypatch.setattr(sa, "_live_check", lambda provider, tid: (sa.FAILED, None))
	sa._settle(frappe._dict(name="SUB-1", payment_provider=sa.CHECKOUT, transaction_id="pr-1"))
	assert ledger["payments"]["SUB-1"].status == sa.FAILED
	assert ledger["company"]["binks"] == {"sitiame_offer": "Essentiel", "sitiame_subscription_ends_on": datetime.date(2026, 10, 30)}


def test_checkout_confirmed_by_jeko_is_checked_against_its_transaction(ledger, monkeypatch):
	"""The return page and the 10-minute job read the amount from
	GET /partner_api/payment_requests/{id} (its "transaction")."""
	ledger["add"]("SUB-1")
	monkeypatch.setattr(sa.jeko_client, "get_payment_request", lambda pid: {"status": "success", "transaction": _paid(25_000)})
	row = frappe._dict(name="SUB-1", payment_provider=sa.CHECKOUT, transaction_id="pr-1")
	assert sa._settle(row) == sa.TO_CHECK
	assert ledger["company"]["binks"]["sitiame_offer"] == "Essentiel"


# -- webhook --


@pytest.fixture
def webhook(ledger, monkeypatch):
	import hashlib
	import hmac

	monkeypatch.setattr(frappe, "conf", CONF, raising=False)
	monkeypatch.setattr(frappe, "response", {}, raising=False)
	state = {"raw": b"", "signature": None}
	monkeypatch.setattr(frappe, "request", frappe._dict(get_data=lambda: state["raw"]), raising=False)
	monkeypatch.setattr(frappe, "get_request_header", lambda name, default=None: state["signature"], raising=False)
	monkeypatch.setattr(sa, "_find_payment", lambda details: "SUB-1" if details.get("id") == "pr-1" or details.get("paymentLinkId") == "pl-1" else None)

	def post(body):
		state["raw"] = json.dumps(body).encode()
		state["signature"] = hmac.new(b"s3cret", state["raw"], hashlib.sha256).hexdigest()
		return sa.jeko_subscription_webhook()

	return post


def test_webhook_received_three_times_activates_once(ledger, webhook):
	ledger["add"]("SUB-1")
	body = {"status": "success", "paymentMethod": "wave", **_paid(45_000), "transactionDetails": {"id": "pr-1", "reference": "SUB-1-abc"}}
	for _ in range(3):
		assert webhook(body) == {"status": "ok"}
	assert ledger["company"]["binks"]["sitiame_subscription_ends_on"] == datetime.date(2026, 11, 14)
	assert len(ledger["offer_roles"]) == 2


def test_webhook_with_a_wrong_amount_activates_nothing(ledger, webhook):
	ledger["add"]("SUB-1", offer="Transformation", amount=250_000)
	webhook({"status": "success", **_paid(45_000), "transactionDetails": {"id": "pr-1"}})
	assert ledger["payments"]["SUB-1"].status == sa.TO_CHECK
	assert ledger["company"]["binks"]["sitiame_offer"] == "Essentiel"


def test_cancelled_payment_activates_nothing(ledger, webhook):
	ledger["add"]("SUB-1")
	webhook({"status": "error", "transactionDetails": {"id": "pr-1"}})
	assert ledger["payments"]["SUB-1"].status == sa.FAILED
	assert ledger["company"]["binks"]["sitiame_subscription_ends_on"] is None


def test_checkout_webhook_without_amount_waits_for_the_jeko_check(ledger, webhook):
	ledger["add"]("SUB-1")
	assert webhook({"status": "success", "transactionDetails": {"id": "pr-1"}}) == {"status": "ok"}
	assert ledger["payments"]["SUB-1"].status == sa.PENDING


def test_link_webhook_without_amount_is_flagged(ledger, webhook):
	ledger["add"]("SUB-1")
	webhook({"status": "success", "transactionDetails": {"paymentLinkId": "pl-1"}})
	assert ledger["payments"]["SUB-1"].status == sa.TO_CHECK


def test_forged_webhook_activates_nothing(ledger, webhook, monkeypatch):
	ledger["add"]("SUB-1")
	monkeypatch.setattr(frappe, "get_request_header", lambda name, default=None: "forged", raising=False)
	monkeypatch.setattr(frappe, "request", frappe._dict(get_data=lambda: json.dumps({"status": "success", **_paid(45_000), "transactionDetails": {"id": "pr-1"}}).encode()), raising=False)
	assert sa.jeko_subscription_webhook() == {"status": "forbidden"}
	assert ledger["payments"]["SUB-1"].status == sa.PENDING
