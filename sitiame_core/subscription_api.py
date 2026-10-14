# -*- coding: utf-8 -*-
# Copyright (c) 2026, Sitiame Capital
# License: MIT

import datetime
import json

import frappe
from frappe import _
from frappe.utils import add_months, getdate, today

from sitiame_core import jeko_client, portfolio
from sitiame_core.roles import CHARGE_AFFAIRES_ROLE
from sitiame_core.tasks import TRIAL_ROLES

# Custom Field on Company (created by sitiame_core.setup.after_migrate).
# ERPNext is the only source of truth for a PME's subscription: the
# subscription is active while this date is today or later.
SUBSCRIPTION_ENDS_FIELD = "sitiame_subscription_ends_on"

# A payment Jèko still reports as undecided after this many days is an
# abandoned checkout (see reconcile_pending_payments).
PENDING_EXPIRES_AFTER_DAYS = 7

# Hard floor: a misconfigured site_config (e.g. leftover test value of 20)
# must never activate a real subscription for less than this amount.
SUBSCRIPTION_AMOUNT_FLOOR = 1000

# Catalogue officiel des offres PME360 : la seule source des prix. Le
# navigateur n'envoie que la clé de l'offre ; le montant payé est toujours
# lu ici (pages Abonnement et Offres PME360 via get_offer_catalog).
# Prix mensuels en FCFA par régime fiscal de la PME :
#   TEE (entreprenant), RME (microentreprise, ex-impôt synthétique),
#   RSI (réel simplifié), RNI (réel normal).
# Les clés sont celles de Company.sitiame_offer (setup.PME360_OFFERS).
PME360_CATALOG = {
	"Essentiel": {
		"label": "PME360 Essentiel",
		"active": True,
		"prices": {"TEE": 15_000, "RME": 25_000, "RSI": 50_000, "RNI": 80_000},
		"color": "#0ea5e9",
		"badge": "",
		"promise": "Vous tenez votre comptabilité, nous la supervisons.",
		"users": "1 utilisateur",
		"pieces": "100 pièces/mois",
		"features": ["Tableau de bord dirigeant", "Facturation & Achats", "Caisse & Mobile Money", "Stock", "Revue mensuelle SITIAME"],
	},
	"Conformite": {
		"label": "PME360 Conformité",
		"active": True,
		"prices": {"TEE": 30_000, "RME": 45_000, "RSI": 85_000, "RNI": 130_000},
		"color": "#8b5cf6",
		"badge": "RECOMMANDÉ",
		"promise": "Vous saisissez, nous certifions et nous déposons.",
		"users": "3 utilisateurs",
		"pieces": "200 pièces/mois",
		"features": ["Tout Essentiel", "Validation des écritures", "Dépôt TVA", "États SYSCOHADA", "Clôture mensuelle", "Expert-comptable référent"],
	},
	"Pilotage": {
		"label": "PME360 Pilotage",
		"active": True,
		"prices": {"TEE": 75_000, "RME": 100_000, "RSI": 175_000, "RNI": 250_000},
		"color": "#f59e0b",
		"badge": "",
		"promise": "Nous tenons votre gestion administrative et financière.",
		"users": "5 utilisateurs",
		"pieces": "300 pièces/mois",
		"features": ["Tout Conformité", "Tenue complète", "Relances clients", "Trésorerie prévisionnelle", "Chargé de compte dédié"],
	},
	"Transformation": {
		"label": "PME360 Transformation",
		"active": True,
		"prices": {"TEE": 200_000, "RME": 250_000, "RSI": 300_000, "RNI": 400_000},
		"color": "#10b981",
		"badge": "PREMIUM",
		"promise": "Nous digitalisons votre gestion et préparons votre financement.",
		"users": "Illimité",
		"pieces": "Illimité",
		"features": ["Tout Pilotage", "Paie & bulletins", "Immobilisations", "Dossier de financement", "Formation équipes", "Comité trimestriel"],
	},
}
REGIMES = ("TEE", "RME", "RSI", "RNI")
REGIME_LABELS = {"TEE": "Entreprenant / TEE", "RME": "Impôt synthétique", "RSI": "Réel simplifié", "RNI": "Réel normal"}
# Company.sitiame_regime_fiscal is empty until the accountant fills it in
# (every PME on 2026-10-14): those pay the "impôt synthétique" column.
DEFAULT_REGIME = "RME"
DEFAULT_OFFER = "Essentiel"
CURRENCY = "XOF"
BILLING_MONTHS = 1


def billing_regime(regime):
	return regime if regime in REGIMES else DEFAULT_REGIME


def check_offer(offer):
	"""The catalogue key of an offer a client asked for, or an error: an
	unknown or withdrawn offer is never priced."""
	entry = PME360_CATALOG.get(offer or "")
	if not entry:
		frappe.throw(_("Offre inconnue : {0}").format(offer), frappe.ValidationError)
	if not entry["active"]:
		frappe.throw(_("L'offre {0} n'est plus proposée.").format(entry["label"]), frappe.ValidationError)
	return offer


def offer_price(offer, regime=None):
	"""Monthly price in FCFA of an offer for a tax regime."""
	return PME360_CATALOG[check_offer(offer)]["prices"][billing_regime(regime)]


def _company_offer_and_regime(company):
	from sitiame_core.setup import PME360_OFFER_FIELD

	row = frappe.db.get_value("Company", company, [PME360_OFFER_FIELD, "sitiame_regime_fiscal"], as_dict=True) or {}
	offer = row.get(PME360_OFFER_FIELD)
	return (offer if offer in PME360_CATALOG else DEFAULT_OFFER), row.get("sitiame_regime_fiscal") or ""


def subscription_amount_for(company=None, offer=None):
	"""Monthly price in FCFA of `offer` (default: the company's current
	offer) at the company's tax regime. site_config
	"sitiame_subscription_amount" forces a flat amount (test mode)."""
	override = frappe.conf.get("sitiame_subscription_amount")
	if override:
		return max(SUBSCRIPTION_AMOUNT_FLOOR, int(override))

	current, regime = _company_offer_and_regime(company) if company else (DEFAULT_OFFER, "")
	return offer_price(offer or current, regime)


def subscription_amount():
	"""Price of the default offer, for callers that have no company."""
	return subscription_amount_for()


def offer_catalog(regime=None):
	"""The offers as the pages show them, priced for one tax regime."""
	regime = billing_regime(regime)
	return [
		{
			"key": key,
			"label": entry["label"],
			"price": entry["prices"][regime],
			"prices": entry["prices"],
			"currency": CURRENCY,
			"months": BILLING_MONTHS,
			**{field: entry[field] for field in ("color", "badge", "promise", "users", "pieces", "features")},
		}
		for key, entry in PME360_CATALOG.items()
		if entry["active"]
	]


@frappe.whitelist()
def get_offer_catalog():
	"""Every active offer with its price for each regime (Offres PME360 page)."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Connexion requise."), frappe.PermissionError)
	return {"offers": offer_catalog(), "regimes": REGIME_LABELS, "default_regime": DEFAULT_REGIME}

# Subscription Payment.payment_provider. Older payments (empty provider)
# came from a previous provider and are no longer queried.
CHECKOUT = "Jèko Checkout"  # the PME pays from the Abonnement page
LINK = "Jèko Lien"  # a single-use link sent by Sitiame staff

PAID, FAILED, PENDING = "Payé", "Échoué", "En attente"
# Jèko confirmed a payment that does not match what was asked (amount,
# currency): nothing is activated, Sitiame staff check it in Jèko.
TO_CHECK = "À vérifier"


def get_user_company(user=None):
	# The Company User Permission is what ties a PME account to its company
	# (both signup paths create it). No fallback on the "default company"
	# user setting: a staff account's default would point at the wrong PME.
	user = user or frappe.session.user
	company = frappe.db.get_value("User Permission", {"user": user, "allow": "Company"}, "for_value")
	if company:
		return company
	# Fallback: Company Signup (handles accounts created before the automated
	# provisioning path or where the User Permission was accidentally removed).
	company = frappe.db.get_value("Company Signup", {"email": user}, "company")
	if company:
		frappe.logger("sitiame_core.boot").warning(
			f"get_user_company: no User Permission for {user!r}, "
			f"fell back to Company Signup -> {company!r}"
		)
	return company


# Staff accounts such as accountants or credit analysts. PME accounts have
# the Accounts Manager role too, but they are tied to their company.
STAFF_ROLES = ("System Manager", CHARGE_AFFAIRES_ROLE)


def is_sitiame_staff(user=None):
	"""Opens the staff view of the Abonnement page (every PME)."""
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if roles.intersection(STAFF_ROLES):
		return True
	return "Accounts Manager" in roles and not get_user_company(user)


def _only_staff():
	if not is_sitiame_staff():
		frappe.throw(_("Réservé au personnel Sitiame."), frappe.PermissionError)


def get_company_subscription(company):
	from sitiame_core.setup import PME360_OFFER_FIELD

	if company:
		row = frappe.db.get_value(
			"Company", company,
			[SUBSCRIPTION_ENDS_FIELD, PME360_OFFER_FIELD, "sitiame_regime_fiscal"],
			as_dict=True,
		) or {}
	else:
		row = {}

	ends_on = row.get(SUBSCRIPTION_ENDS_FIELD)
	trial_ends_on = frappe.db.get_value("Company Signup", {"company": company}, "trial_ends_on") if company else None

	return {
		"company": company,
		"ends_on": str(ends_on) if ends_on else None,
		"active": bool(ends_on and getdate(ends_on) >= getdate(today())),
		"trial_ends_on": str(trial_ends_on) if trial_ends_on else None,
		"in_trial": bool(trial_ends_on and getdate(trial_ends_on) >= getdate(today())),
		"offer": row.get(PME360_OFFER_FIELD) or "Essentiel",
		"regime": row.get("sitiame_regime_fiscal") or "",
	}


def _amount_mismatch(doc, paid):
	"""Why a payment Jèko reports as successful does not settle `doc`, or
	None when it matches. `paid` is Jèko's transaction amount:
	{"amount": {"amount", "currency"}, "fees": {"amount", ...}}. Jèko's docs
	state neither the unit of that amount (requests are in "cents") nor
	whether it is net of fees, so the expected price is accepted in FCFA
	or in cents, gross or net of the fees -- anything else is refused."""
	money = (paid or {}).get("amount")
	if not isinstance(money, dict) or money.get("amount") in (None, ""):
		return _("Jèko n'a pas transmis le montant payé.")

	expected_currency = doc.get("currency") or CURRENCY
	if (money.get("currency") or "").upper() != expected_currency:
		return _("Devise payée {0}, attendue {1}.").format(money.get("currency"), expected_currency)

	try:
		amount = float(money["amount"])
		fees = float(((paid.get("fees") or {}).get("amount")) or 0)
	except (TypeError, ValueError):
		return _("Montant payé illisible : {0}.").format(money.get("amount"))

	expected = int(round(float(doc.amount or 0)))
	if expected and any(round(value) in (expected, expected * 100) for value in (amount, amount + fees)):
		return None
	return _("Montant payé {0}, attendu {1} FCFA.").format(money.get("amount"), expected)


def _flag_to_check(docname, reason):
	frappe.db.set_value("Subscription Payment", docname, {"status": TO_CHECK, "verification_note": reason})
	frappe.db.commit()
	frappe.log_error(title="Jèko : paiement à vérifier", message=f"{docname} : {reason}")


def _apply_paid_offer(doc):
	"""The offer the PME paid for becomes its offer, and every account of
	the PME gets the matching offer role (offer_access.py checks the role).
	Payments made before the offer was recorded leave the offer as is."""
	from sitiame_core.offer_roles import sync_offer_role
	from sitiame_core.setup import PME360_OFFER_FIELD

	if doc.get("offer") not in PME360_CATALOG:
		return
	frappe.db.set_value("Company", doc.company, PME360_OFFER_FIELD, doc.offer)
	for user in frappe.get_all(
		"User Permission", filters={"allow": "Company", "for_value": doc.company}, pluck="user"
	):
		if "PME Client" in frappe.get_roles(user):
			sync_offer_role(user, doc.offer)


def _mark_paid(docname, paid=None):
	"""Single entry point once Jèko confirms a payment (webhook, return
	page, 10-minute check): checks the amount Jèko reports (`paid`, see
	_amount_mismatch), flags the Subscription Payment as paid, switches the
	PME to the offer it paid for, extends the Company's subscription and
	gives back any access the trial expiry had removed. Row-locked so the
	webhook and the return page racing each other can never extend the
	subscription twice. Returns True when the payment is (now) paid."""
	status = frappe.db.get_value("Subscription Payment", docname, "status", for_update=True)
	if status == PAID:
		return True

	doc = frappe.get_doc("Subscription Payment", docname)
	reason = _amount_mismatch(doc, paid)
	if reason:
		_flag_to_check(docname, reason)
		return False

	doc.db_set("status", PAID)
	doc.db_set("paid_at", frappe.utils.now())
	_apply_paid_offer(doc)

	# Stack on top of whatever access the PME still has (running
	# subscription or free trial) so paying early never loses days.
	current = get_company_subscription(doc.company)
	start = getdate(today())
	for date in (current["ends_on"], current["trial_ends_on"]):
		if date and getdate(date) > start:
			start = getdate(date)
	end = add_months(start, doc.duration_months or 1)
	frappe.db.set_value("Company", doc.company, SUBSCRIPTION_ENDS_FIELD, end)
	# printed on the receipt
	doc.db_set("period_start", start)
	doc.db_set("period_end", end)

	_restore_trial_roles(doc.company)
	frappe.db.commit()
	return True


def _restore_trial_roles(company):
	for signup in frappe.get_all(
		"Company Signup", filters={"company": company, "trial_blocked": 1}, fields=["name", "email"]
	):
		if frappe.db.exists("User", signup.email):
			user = frappe.get_doc("User", signup.email)
			# the Jèko webhook runs as Guest
			user.flags.ignore_permissions = True
			user.add_roles(*TRIAL_ROLES)
		frappe.db.set_value("Company Signup", signup.name, "trial_blocked", 0)


@frappe.whitelist()
def get_my_subscription():
	if frappe.session.user == "Guest":
		frappe.throw(_("Connexion requise."), frappe.PermissionError)
	company = get_user_company()
	return {
		**_priced_subscription(company),
		"is_staff": is_sitiame_staff(),
		"is_admin": "System Manager" in frappe.get_roles(),
	}


def _priced_subscription(company):
	"""A company's subscription, with the offers priced at its regime."""
	sub = get_company_subscription(company)
	return {
		**sub,
		"amount": subscription_amount_for(company) if company else None,
		"billing_regime": billing_regime(sub["regime"]),
		"billing_regime_label": REGIME_LABELS[billing_regime(sub["regime"])],
		"offers": offer_catalog(sub["regime"]),
	}


# -- Creating payments --


def _new_payment(company, offer=None):
	"""A pending payment for `offer` (default: the company's current offer),
	priced here from the catalogue. The offer is only applied to the
	company once Jèko confirms the payment (_mark_paid)."""
	current, regime = _company_offer_and_regime(company)
	offer = check_offer(offer or current)
	doc = frappe.get_doc(
		{
			"doctype": "Subscription Payment",
			"company": company,
			"offer": offer,
			"regime": billing_regime(regime),
			"amount": subscription_amount_for(company, offer),
			"currency": CURRENCY,
			"duration_months": BILLING_MONTHS,
			"status": PENDING,
		}
	)
	# the caller creates the Jèko side itself (after_insert would make a
	# staff link)
	doc.flags.skip_payment_link = True
	doc.insert(ignore_permissions=True)
	return doc


def _create_checkout(doc, payment_method):
	"""Jèko Checkout for a PME paying from the Abonnement page: back on
	that page once paid (or not)."""
	base = f"{frappe.utils.get_url()}/desk/erp-abonnement?docname={doc.name}&payment_status="
	# Jèko refuses a reference it has already seen, and a document name
	# can come back (a rolled-back insert reuses its number): a suffix
	# keeps every attempt unique.
	reference = f"{doc.name}-{frappe.generate_hash(length=6)}"
	result = jeko_client.create_payment_request(reference, doc.amount, payment_method, base + "success", base + "failed")
	_save_payment(doc, CHECKOUT, result.get("id"), result.get("redirectUrl"), payment_method)
	return result.get("redirectUrl")


def _create_link(doc):
	"""Single-use Jèko payment link, for Sitiame staff to send to the PME:
	the payer picks the operator on Jèko's page."""
	offer = PME360_CATALOG.get(doc.get("offer") or "", {}).get("label") or "Abonnement Sitiame"
	result = jeko_client.create_payment_link(f"{offer} - {doc.company}", doc.amount)
	_save_payment(doc, LINK, result.get("id"), result.get("link"))
	return result.get("link")


def _save_payment(doc, provider, transaction_id, payment_url, payment_method=None):
	if not transaction_id or not payment_url:
		frappe.throw(_("Jèko n'a pas renvoye de lien de paiement."))
	doc.db_set("payment_provider", provider)
	doc.db_set("transaction_id", transaction_id)
	doc.db_set("payment_url", payment_url)
	if payment_method:
		doc.db_set("payment_method", payment_method)
	frappe.db.commit()


@frappe.whitelist()
def generate_subscription_payment_link(docname):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Reserve aux administrateurs."), frappe.PermissionError)

	doc = frappe.get_doc("Subscription Payment", docname)
	return {"payment_url": _create_link(doc)}


def generate_payment_link_on_insert(doc):
	"""A Subscription Payment created by hand in the desk gets its staff
	link at once."""
	if doc.flags.skip_payment_link:
		return
	try:
		_create_link(doc)
	except Exception:
		frappe.log_error(
			title="Subscription Payment: generation automatique du lien echouee",
			message=frappe.get_traceback(),
		)


SITIAME_COMPANY = "SITIAME"


def _paying_company(company=None):
	"""A PME account always pays for its own company, whatever it sends.
	A Sitiame staff account (no company of its own) picks the PME: any
	of them, or those of his portfolio for a chargé d'affaires."""
	own = get_user_company()
	if own:
		return own
	if not company:
		if is_sitiame_staff():
			frappe.throw(_("Choisissez d'abord la PME (champ « Société »)."))
		frappe.throw(
			_("L'abonnement se paie depuis le compte de la PME : aucune societe n'est rattachee a votre compte.")
		)
	_only_staff()
	if company == SITIAME_COMPANY or not frappe.db.exists("Company", company):
		frappe.throw(_("Societe introuvable : {0}").format(company))
	portfolio.check_company(company)
	return company


@frappe.whitelist()
def get_company_subscription_for(company):
	"""Staff paying for a PME: that PME's current state and prices."""
	return _priced_subscription(_paying_company(company))


@frappe.whitelist()
def get_or_create_pme_checkout_url(payment_method=None, force_new=0, company=None, offer=None):
	"""The PME pays its own subscription with the operator it picked on
	the Abonnement page; Sitiame staff pick the PME first (`company`).
	force_new is ignored (kept for old clients). offer: the catalogue key
	the client picked (default: its current offer). Only the key comes from
	the browser: the price is the catalogue's, and the offer is applied to
	the company once the payment is confirmed, never before."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Connexion requise."), frappe.PermissionError)

	company = _paying_company(company)
	if payment_method not in jeko_client.PAYMENT_METHODS:
		frappe.throw(_("Choisissez votre moyen de paiement (Wave, Orange Money, MTN, Moov ou Djamo)."))
	if offer:
		check_offer(offer)

	# A payment still open may have gone through in the meantime: never
	# make the PME pay twice.
	for row in frappe.get_all(
		"Subscription Payment",
		filters={"company": company, "status": PENDING, "transaction_id": ["is", "set"]},
		fields=["name", "payment_provider", "transaction_id"],
		order_by="creation desc",
		limit=3,
	):
		if _settle(row) == PAID:
			return {"status": PAID, "already_paid": True, "docname": row.name, "company": company}

	doc = _new_payment(company, offer)
	return {
		"payment_url": _create_checkout(doc, payment_method),
		"docname": doc.name,
		"company": company,
		"is_new": True,
	}


@frappe.whitelist()
def create_company_payment_link(company, offer=None):
	"""Sitiame staff: always a fresh single-use Jèko link for the chosen
	PME and offer (default: its current offer), to send it to them
	(WhatsApp, e-mail...). A chargé d'affaires: for a PME of his portfolio."""
	_only_staff()
	if not frappe.db.exists("Company", company):
		frappe.throw(_("Societe introuvable : {0}").format(company))
	portfolio.check_company(company)
	doc = _new_payment(company, offer)
	return {
		"payment_url": _create_link(doc),
		"docname": doc.name,
		"company": company,
		"offer": doc.offer,
		"amount": doc.amount,
		"is_new": True,
	}


@frappe.whitelist()
def list_company_subscriptions():
	"""Sitiame staff overview: every PME company with its subscription state
	and paid history (a chargé d'affaires: his portfolio)."""
	_only_staff()

	paid = {}
	for row in frappe.get_all(
		"Subscription Payment", filters={"status": PAID}, fields=["company", "paid_at"]
	):
		history = paid.setdefault(row.company, {"paid_count": 0, "last_paid_at": None})
		history["paid_count"] += 1
		if row.paid_at and (not history["last_paid_at"] or row.paid_at > history["last_paid_at"]):
			history["last_paid_at"] = row.paid_at

	pme_companies = {
		row.for_value
		for row in frappe.get_all("User Permission", filters={"allow": "Company"}, fields=["for_value"])
	}

	companies = pme_companies | set(paid)
	if portfolio.is_charge_affaires():
		companies &= portfolio.portfolio()

	rows = []
	for company in sorted(companies):
		sub = get_company_subscription(company)
		history = paid.get(company) or {}
		if sub["active"]:
			state = "Actif"
		elif sub["in_trial"]:
			state = "Essai"
		elif sub["ends_on"]:
			state = "Expiré"
		else:
			state = "Aucun"
		rows.append(
			{
				**sub,
				"state": state,
				"paid_count": history.get("paid_count") or 0,
				"last_paid_at": str(history["last_paid_at"]) if history.get("last_paid_at") else None,
			}
		)
	return rows


# -- Following payments --


def _live_status(provider, transaction_id):
	"""What Jèko says now: PAID, FAILED, PENDING, or LINK_CLOSED."""
	return _live_check(provider, transaction_id)[0]


def _live_check(provider, transaction_id):
	"""(status, paid): _live_status's answer, plus the transaction Jèko
	attached to a paid checkout (its amount and fees, see _amount_mismatch)."""
	if provider == CHECKOUT:
		data = jeko_client.get_payment_request(transaction_id)
		status = {"success": PAID, "error": FAILED}.get((data.get("status") or "").lower(), PENDING)
		return status, data.get("transaction") if status == PAID else None
	return _link_status(provider, transaction_id), None


def _link_status(provider, transaction_id):
	if provider == LINK:
		# A link is only ever paid by its signed "success" webhook. Jèko
		# answers canReceivePayments = false for a used link, but also for
		# an expired or disabled one (docs: payments/payment-links), and
		# its transaction list carries no paymentLinkId: taking false for
		# "paid" gave a free month whenever a link expired unpaid.
		if jeko_client.get_payment_link(transaction_id).get("canReceivePayments") is False:
			return LINK_CLOSED
		return PENDING
	# older payments (previous provider): no longer queried, expire with age
	return PENDING


# Internal answer of _live_status: the link no longer accepts payments, and
# nothing proves it was paid. Left pending for Sitiame staff to check in
# the Jèko dashboard, never marked paid or failed automatically.
LINK_CLOSED = "link_closed"
LINK_CHECK_LOG_TTL = 7 * 24 * 3600


def _flag_closed_link(name):
	"""Error Log once a week per payment, not every 10 minutes."""
	key = f"sitiame_core:jeko_link_to_check:{name}"
	if frappe.cache().get_value(key):
		return
	frappe.cache().set_value(key, 1, expires_in_sec=LINK_CHECK_LOG_TTL)
	frappe.log_error(
		title="Jèko : lien de paiement a verifier",
		message=_(
			"{0} : le lien Jèko n'accepte plus de paiement (paye, expire ou desactive) et aucun webhook de paiement "
			"n'a ete recu. Verifiez dans le tableau de bord Jèko avant toute action : rien n'a ete modifie."
		).format(name),
	)


def _settle(row):
	"""Applies Jèko's current answer to a pending payment; returns it
	(TO_CHECK when Jèko's paid amount does not match the payment)."""
	status, paid = _live_check(row.payment_provider, row.transaction_id)
	if status == PAID:
		if not _mark_paid(row.name, paid):
			status = TO_CHECK
	elif status == FAILED:
		frappe.db.set_value("Subscription Payment", row.name, "status", FAILED)
		frappe.db.commit()
	elif status == LINK_CLOSED:
		_flag_closed_link(row.name)
		status = PENDING
	return status


@frappe.whitelist()
def check_pme_subscription_status(docname=None):
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Connexion requise."), frappe.PermissionError)

	if docname and frappe.db.exists("Subscription Payment", docname):
		doc = frappe.get_doc("Subscription Payment", docname)
		# a PME may only look at its own company's payments (amount, link)
		_check_receipt_access(doc)

		if doc.status == PENDING and doc.transaction_id:
			try:
				_settle(doc)
				doc.reload()
			except Exception:
				# Jèko unreachable: the webhook or the 10-minute check settles it
				pass

		return {
			"status": doc.status,
			"paid_at": str(doc.paid_at) if doc.paid_at else None,
			"company": doc.company,
			"amount": doc.amount,
			"payment_url": doc.payment_url,
			"subscription": get_company_subscription(doc.company),
		}

	company = get_user_company(user)
	if not company:
		return {"status": "unknown"}

	last = frappe.get_all(
		"Subscription Payment",
		filters={"company": company},
		fields=["name", "status", "paid_at", "amount", "payment_url"],
		order_by="creation desc",
		limit=1,
	)
	if last:
		return {
			"docname": last[0]["name"],
			"status": last[0]["status"],
			"paid_at": str(last[0]["paid_at"]) if last[0].get("paid_at") else None,
			"company": company,
			"amount": last[0].get("amount"),
			"payment_url": last[0].get("payment_url"),
		}
	return {"status": "none", "company": company}


def _find_payment(details):
	"""The Subscription Payment a Jèko transaction belongs to, or None."""
	if details.get("paymentLinkId"):
		return frappe.db.get_value(
			"Subscription Payment", {"payment_provider": LINK, "transaction_id": details["paymentLinkId"]}, "name"
		)
	if details.get("id"):
		name = frappe.db.get_value(
			"Subscription Payment", {"payment_provider": CHECKOUT, "transaction_id": details["id"]}, "name"
		)
		# the reference we sent is the document name, plus a suffix since
		# 2026-09-30 (older checkouts carry the bare name)
		reference = details.get("reference")
		if name and (not reference or reference == name or reference.startswith(name + "-")):
			return name
	return None


@frappe.whitelist(allow_guest=True)
def jeko_subscription_webhook():
	"""Jèko posts the transaction itself (no envelope), signed with
	Jeko-Signature = HMAC-SHA256 of the raw body. Answers fast (Jèko waits 5
	s): the signed body is trusted, no call back to Jèko. Transactions of
	other stores or products are acknowledged and ignored."""
	# Optional IP allowlist: set "jeko_allowed_ips": ["x.x.x.x", ...] in
	# site_config.json to restrict this endpoint to Jèko's servers.
	allowed_ips = frappe.conf.get("jeko_allowed_ips")
	if allowed_ips:
		client_ip = (
			frappe.get_request_header("X-Real-IP")
			or frappe.get_request_header("X-Forwarded-For", "").split(",")[0].strip()
			or (frappe.request.remote_addr if frappe.request else "")
		)
		if client_ip not in allowed_ips:
			frappe.log_error(title="Jèko webhook: IP non autorisée", message=f"IP: {client_ip!r}")
			frappe.response["http_status_code"] = 403
			return {"status": "forbidden"}
	raw_body = frappe.request.get_data() if frappe.request else b""
	if not jeko_client.valid_signature(raw_body, frappe.get_request_header("Jeko-Signature")):
		frappe.log_error(title="Jèko webhook: signature invalide", message=(raw_body or b"")[:500])
		frappe.response["http_status_code"] = 401
		return {"status": "forbidden"}

	try:
		body = json.loads(raw_body)
	except ValueError:
		frappe.response["http_status_code"] = 400
		return {"status": "bad request"}

	name = _find_payment(body.get("transactionDetails") or {}) if isinstance(body, dict) else None
	if not name:
		return {"status": "ignored"}

	status = (body.get("status") or "").lower()
	if status == "success":
		if body.get("paymentMethod") and not frappe.db.get_value("Subscription Payment", name, "payment_method"):
			frappe.db.set_value("Subscription Payment", name, "payment_method", body["paymentMethod"])
		if body.get("amount") is None and not (body.get("transactionDetails") or {}).get("paymentLinkId"):
			# a checkout's amount is read from Jèko by the 10-minute check
			# (_settle); a link has no other proof, so _mark_paid flags it
			return {"status": "ok"}
		_mark_paid(name, {"amount": body.get("amount"), "fees": body.get("fees")})
	elif status == "error" and frappe.db.get_value("Subscription Payment", name, "status") == PENDING:
		frappe.db.set_value("Subscription Payment", name, "status", FAILED)
		frappe.db.commit()
	return {"status": "ok"}


def reconcile_pending_payments():
	"""Scheduler job (every 10 min, see hooks.py): settle payments still "En
	attente" by asking Jèko directly. The webhook is the fast path, but it
	can be lost (Jèko gives up after 3 attempts); without this, a paid
	subscription stayed inactive unless the customer came back to the
	Abonnement page.

	Every pending payment is checked, whatever its age. One still undecided
	after PENDING_EXPIRES_AFTER_DAYS is an abandoned checkout, closed as
	failed so it stops being polled."""
	expire_before = frappe.utils.now_datetime() - datetime.timedelta(days=PENDING_EXPIRES_AFTER_DAYS)
	for row in frappe.get_all(
		"Subscription Payment",
		filters={"status": PENDING, "transaction_id": ["is", "set"]},
		fields=["name", "creation", "payment_provider", "transaction_id"],
	):
		try:
			# A staff link is never closed as failed automatically: it may
			# have been paid with its webhook lost (see _live_status).
			if _settle(row) == PENDING and row.creation < expire_before and row.payment_provider != LINK:
				frappe.db.set_value("Subscription Payment", row.name, "status", FAILED)
				frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title="Subscription Payment: reconciliation echouee",
				message=f"{row.name}\n{frappe.get_traceback()}",
			)


# -- Receipts --

RECEIPT_TEMPLATE = "sitiame_core/templates/subscription_receipt.html"

# Subscription Payment.payment_method as Jèko sends it
METHOD_LABELS = {"wave": "Wave", "orange": "Orange Money", "mtn": "MTN MoMo", "moov": "Moov Money", "djamo": "Djamo"}


def _check_receipt_access(doc):
	"""A PME: its own company's payments. Sitiame staff: every PME, a
	chargé d'affaires his portfolio only."""
	if doc.company and doc.company == get_user_company():
		return
	if is_sitiame_staff():
		portfolio.check_company(doc.company)
		return
	frappe.throw(_("Ce paiement ne concerne pas votre societe."), frappe.PermissionError)


def format_fcfa(amount):
	return f"{int(round(amount or 0)):,}".replace(",", " ") + " FCFA"


def amount_in_words(amount):
	"""« vingt mille francs CFA », as French receipts state the total."""
	try:
		from num2words import num2words

		return f"{num2words(int(round(amount or 0)), lang='fr')} francs CFA"
	except Exception:
		return format_fcfa(amount)


def _logo_data_uri():
	# embedded: wkhtmltopdf would otherwise have to fetch it over HTTP
	import base64
	import os

	path = os.path.join(os.path.dirname(__file__), "public", "images", "sitiame-capital-logo.png")
	try:
		with open(path, "rb") as f:
			return "data:image/png;base64," + base64.b64encode(f.read()).decode()
	except OSError:
		return None


def _customer(company):
	"""The PME as it signed up: contact, account e-mail, phone, address."""
	signup = frappe.db.get_value(
		"Company Signup",
		{"company": company},
		["contact_name", "email", "phone", "company_sigle", "sector", "rccm", "address", "city"],
		as_dict=True,
	) or frappe._dict()
	country = frappe.db.get_value("Company", company, "country")
	if country == "Ivory Coast":
		country = "Côte d'Ivoire"
	signup.location = ", ".join(x for x in (signup.address, signup.city, country) if x)
	return signup


def receipt_context(doc):
	method = (doc.payment_method or "").lower()

	def date(value):
		return frappe.utils.formatdate(value, "dd/MM/yyyy") if value else ""

	return {
		"doc": doc,
		"customer": _customer(doc.company),
		"amount": format_fcfa(doc.amount),
		"amount_in_words": amount_in_words(doc.amount),
		"paid_at": frappe.utils.format_datetime(doc.paid_at, "dd/MM/yyyy à HH:mm") if doc.paid_at else "",
		"paid_date": date(doc.paid_at),
		"method": METHOD_LABELS.get(method, doc.payment_method or "Mobile Money"),
		"channel": _("Lien de paiement") if doc.payment_provider == LINK else _("Paiement en ligne"),
		"months": doc.duration_months or 1,
		"period_start": date(doc.get("period_start")),
		"period_end": date(doc.get("period_end")),
		"logo": _logo_data_uri(),
		# site_config "sitiame_receipt_issuer": lines under the logo (address, phone, RCCM...)
		"issuer_lines": frappe.conf.get("sitiame_receipt_issuer") or ["Côte d'Ivoire", "erp.sitiame-capital.com"],
		"generated_at": frappe.utils.format_datetime(frappe.utils.now_datetime(), "dd/MM/yyyy à HH:mm"),
	}


@frappe.whitelist()
def download_receipt(docname):
	"""PDF receipt of a paid subscription payment."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Connexion requise."), frappe.PermissionError)
	if not frappe.db.exists("Subscription Payment", docname):
		frappe.throw(_("Paiement introuvable : {0}").format(docname))
	doc = frappe.get_doc("Subscription Payment", docname)
	_check_receipt_access(doc)
	if doc.status != PAID:
		frappe.throw(_("Le reçu est disponible une fois le paiement confirmé."))

	from frappe.utils.pdf import get_pdf

	html = frappe.render_template(RECEIPT_TEMPLATE, receipt_context(doc))
	frappe.local.response.filename = f"Recu-{doc.name}.pdf"
	frappe.local.response.filecontent = get_pdf(html)
	frappe.local.response.type = "download"


@frappe.whitelist()
def list_my_receipts(company=None):
	"""The PME's paid payments, newest first, for the Abonnement page
	(staff: those of the PME they picked)."""
	if not get_user_company() and not company:
		return []
	company = _paying_company(company)
	return frappe.get_all(
		"Subscription Payment",
		filters={"company": company, "status": PAID},
		fields=["name", "paid_at", "amount", "payment_method", "duration_months"],
		order_by="paid_at desc",
		ignore_permissions=True,
	)
