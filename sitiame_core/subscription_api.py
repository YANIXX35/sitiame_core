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

# Monthly price in FCFA. site_config "sitiame_subscription_amount" overrides
# it, e.g. 20 for a real low-cost payment test (Jèko has no sandbox).
SUBSCRIPTION_AMOUNT = 15000


def subscription_amount():
	return int(frappe.conf.get("sitiame_subscription_amount") or SUBSCRIPTION_AMOUNT)

# Subscription Payment.payment_provider. Older payments (empty provider)
# came from a previous provider and are no longer queried.
CHECKOUT = "Jèko Checkout"  # the PME pays from the Abonnement page
LINK = "Jèko Lien"  # a single-use link sent by Sitiame staff

PAID, FAILED, PENDING = "Payé", "Échoué", "En attente"


def get_user_company(user=None):
	# The Company User Permission is what ties a PME account to its company
	# (both signup paths create it). No fallback on the "default company"
	# user setting: a staff account's default would point at the wrong PME.
	user = user or frappe.session.user
	return frappe.db.get_value("User Permission", {"user": user, "allow": "Company"}, "for_value")


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
	ends_on = frappe.db.get_value("Company", company, SUBSCRIPTION_ENDS_FIELD) if company else None
	trial_ends_on = frappe.db.get_value("Company Signup", {"company": company}, "trial_ends_on") if company else None

	return {
		"company": company,
		"ends_on": str(ends_on) if ends_on else None,
		"active": bool(ends_on and getdate(ends_on) >= getdate(today())),
		"trial_ends_on": str(trial_ends_on) if trial_ends_on else None,
		"in_trial": bool(trial_ends_on and getdate(trial_ends_on) >= getdate(today())),
	}


def _mark_paid(docname):
	"""Single entry point once Jèko confirms a payment (webhook, return
	page, 10-minute check): flags the Subscription Payment as paid,
	extends the Company's subscription and gives back any access the
	trial expiry had removed. Row-locked so the webhook and the return page
	racing each other can never extend the subscription twice."""
	status = frappe.db.get_value("Subscription Payment", docname, "status", for_update=True)
	if status == PAID:
		return

	doc = frappe.get_doc("Subscription Payment", docname)
	doc.db_set("status", PAID)
	doc.db_set("paid_at", frappe.utils.now())

	# Stack on top of whatever access the PME still has (running
	# subscription or free trial) so paying early never loses days.
	current = get_company_subscription(doc.company)
	start = getdate(today())
	for date in (current["ends_on"], current["trial_ends_on"]):
		if date and getdate(date) > start:
			start = getdate(date)
	frappe.db.set_value("Company", doc.company, SUBSCRIPTION_ENDS_FIELD, add_months(start, doc.duration_months or 1))

	_restore_trial_roles(doc.company)
	frappe.db.commit()


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
	# the price comes along so the pages show what will really be charged
	return {
		**get_company_subscription(get_user_company()),
		"amount": subscription_amount(),
		"is_staff": is_sitiame_staff(),
	}


# -- Creating payments --


def _new_payment(company):
	doc = frappe.get_doc(
		{
			"doctype": "Subscription Payment",
			"company": company,
			"amount": subscription_amount(),
			"duration_months": 1,
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
	result = jeko_client.create_payment_link(f"Abonnement Sitiame - {doc.company}", doc.amount)
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


@frappe.whitelist()
def get_or_create_pme_checkout_url(payment_method=None, force_new=0):
	"""The PME pays its own subscription with the operator it picked on
	the Abonnement page. force_new is ignored (kept for old clients)."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Connexion requise."), frappe.PermissionError)

	# Only a PME account pays for its own company: a Sitiame staff account
	# with no company must never open a checkout on some other PME's behalf.
	company = get_user_company(user)
	if not company:
		frappe.throw(
			_("L'abonnement se paie depuis le compte de la PME : aucune societe n'est rattachee a votre compte.")
		)
	if payment_method not in jeko_client.PAYMENT_METHODS:
		frappe.throw(_("Choisissez votre moyen de paiement (Wave, Orange Money, MTN, Moov ou Djamo)."))

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

	doc = _new_payment(company)
	return {
		"payment_url": _create_checkout(doc, payment_method),
		"docname": doc.name,
		"company": company,
		"is_new": True,
	}


@frappe.whitelist()
def create_company_payment_link(company):
	"""Sitiame staff: always a fresh single-use Jèko link for the chosen
	PME, to send it to them (WhatsApp, e-mail...). A chargé d'affaires:
	for a PME of his portfolio."""
	_only_staff()
	if not frappe.db.exists("Company", company):
		frappe.throw(_("Societe introuvable : {0}").format(company))
	portfolio.check_company(company)
	doc = _new_payment(company)
	return {"payment_url": _create_link(doc), "docname": doc.name, "company": company, "is_new": True}


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
	"""What Jèko says now: PAID, FAILED or PENDING."""
	if provider == CHECKOUT:
		status = (jeko_client.get_payment_request(transaction_id).get("status") or "").lower()
		return {"success": PAID, "error": FAILED}.get(status, PENDING)
	if provider == LINK:
		# a single-use link that no longer accepts payments has been paid
		return PAID if jeko_client.get_payment_link(transaction_id).get("canReceivePayments") is False else PENDING
	# older payments (previous provider): no longer queried, expire with age
	return PENDING


def _settle(row):
	"""Applies Jèko's current answer to a pending payment; returns it."""
	status = _live_status(row.payment_provider, row.transaction_id)
	if status == PAID:
		_mark_paid(row.name)
	elif status == FAILED:
		frappe.db.set_value("Subscription Payment", row.name, "status", FAILED)
		frappe.db.commit()
	return status


@frappe.whitelist()
def check_pme_subscription_status(docname=None):
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Connexion requise."), frappe.PermissionError)

	if docname and frappe.db.exists("Subscription Payment", docname):
		doc = frappe.get_doc("Subscription Payment", docname)
		# a PME may only look at its own company's payments (amount, link)
		if "System Manager" not in frappe.get_roles() and doc.company != get_user_company(user):
			frappe.throw(_("Ce paiement ne concerne pas votre societe."), frappe.PermissionError)

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
		_mark_paid(name)
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
			if _settle(row) == PENDING and row.creation < expire_before:
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


def receipt_context(doc):
	method = (doc.payment_method or "").lower()
	return {
		"doc": doc,
		"amount": format_fcfa(doc.amount),
		"paid_at": frappe.utils.format_datetime(doc.paid_at, "dd/MM/yyyy HH:mm") if doc.paid_at else "",
		"method": METHOD_LABELS.get(method, doc.payment_method or ""),
		"months": doc.duration_months or 1,
		"generated_at": frappe.utils.format_datetime(frappe.utils.now_datetime(), "dd/MM/yyyy HH:mm"),
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
def list_my_receipts():
	"""The PME's paid payments, newest first, for the Abonnement page."""
	company = get_user_company()
	if not company:
		return []
	return frappe.get_all(
		"Subscription Payment",
		filters={"company": company, "status": PAID},
		fields=["name", "paid_at", "amount", "payment_method", "duration_months"],
		order_by="paid_at desc",
		ignore_permissions=True,
	)
