# -*- coding: utf-8 -*-
# Copyright (c) 2026, Sitiame Capital
# License: MIT

import hmac

import frappe
from frappe import _
from frappe.utils import add_months, getdate, today

from sitiame_core.cinetpay_client import get_payment_status, init_payment
from sitiame_core.tasks import TRIAL_ROLES

# Custom Field on Company (created by sitiame_core.setup.after_migrate).
# ERPNext is the only source of truth for a PME's subscription: the
# subscription is active while this date is today or later.
SUBSCRIPTION_ENDS_FIELD = "sitiame_subscription_ends_on"


def get_user_company(user=None):
	# The Company User Permission is what ties a PME account to its company
	# (both signup paths create it). No fallback on the "default company"
	# user setting: a staff account's default would point at the wrong PME.
	user = user or frappe.session.user
	return frappe.db.get_value("User Permission", {"user": user, "allow": "Company"}, "for_value")


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
	"""Single entry point once CinetPay confirms a payment (webhook, return
	page, pending-session check): flags the Subscription Payment as paid,
	extends the Company's subscription and gives back any access the
	trial expiry had removed. Row-locked so the webhook and the return page
	racing each other can never extend the subscription twice."""
	status = frappe.db.get_value("Subscription Payment", docname, "status", for_update=True)
	if status == "Payé":
		return

	doc = frappe.get_doc("Subscription Payment", docname)
	doc.db_set("status", "Payé")
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
			# the CinetPay webhook runs as Guest
			user.flags.ignore_permissions = True
			user.add_roles(*TRIAL_ROLES)
		frappe.db.set_value("Company Signup", signup.name, "trial_blocked", 0)


@frappe.whitelist()
def get_my_subscription():
	if frappe.session.user == "Guest":
		frappe.throw(_("Connexion requise."), frappe.PermissionError)
	return get_company_subscription(get_user_company())


def _generate_payment_link(doc):
	site_url = frappe.utils.get_url()

	notify_token = doc.notify_token or frappe.generate_hash(length=32)
	doc.db_set("notify_token", notify_token)

	notify_url = f"{site_url}/api/method/sitiame_core.subscription_api.cinetpay_subscription_webhook?token={notify_token}&docname={doc.name}"
	success_url = f"{site_url}/app/erp-abonnement?docname={doc.name}&cinetpay_status=success"
	failed_url = f"{site_url}/app/erp-abonnement?docname={doc.name}&cinetpay_status=failed"

	customer = {}
	user_email = doc.owner or frappe.session.user
	if user_email and frappe.db.exists("User", user_email):
		user_doc = frappe.get_doc("User", user_email)
		customer["first_name"] = user_doc.first_name or "Client"
		customer["last_name"] = user_doc.last_name or doc.company
		if user_doc.email and "@" in user_doc.email and not user_doc.email.endswith("@example.com"):
			customer["email"] = user_doc.email
		if getattr(user_doc, "mobile_no", None) or getattr(user_doc, "phone", None):
			customer["phone"] = user_doc.mobile_no or user_doc.phone

	result = init_payment(
		merchant_transaction_id=doc.name,
		amount=doc.amount,
		designation=f"Abonnement premium Sitiame - {doc.company}",
		notify_url=notify_url,
		success_url=success_url,
		failed_url=failed_url,
		customer=customer,
	)

	payment_token = result.get("payment_token")
	payment_url = result.get("payment_url")
	if not payment_url and payment_token:
		payment_url = f"https://secure.cinetpay.net/checkout/{payment_token}"

	doc.db_set("transaction_id", result.get("transaction_id"))
	doc.db_set("payment_url", payment_url)
	frappe.db.commit()

	return {"payment_url": payment_url}


@frappe.whitelist()
def generate_subscription_payment_link(docname):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Reserve aux administrateurs."), frappe.PermissionError)

	doc = frappe.get_doc("Subscription Payment", docname)
	return _generate_payment_link(doc)


def generate_payment_link_on_insert(doc):
	try:
		_generate_payment_link(doc)
	except Exception:
		frappe.log_error(
			title="Subscription Payment: generation automatique du lien echouee",
			message=frappe.get_traceback(),
		)


@frappe.whitelist()
def get_or_create_pme_checkout_url(force_new=0):
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

	force = int(force_new or 0)

	if not force:
		existing = frappe.get_all(
			"Subscription Payment",
			filters={
				"company": company,
				"status": "En attente",
			},
			fields=["name", "payment_url", "creation"],
			order_by="creation desc",
			limit=1,
		)
		if existing and existing[0].get("payment_url"):
			existing_name = existing[0]["name"]
			existing_creation = existing[0].get("creation")

			# Check transaction age (sessions expire on CinetPay in ~15 minutes)
			is_fresh = False
			if existing_creation:
				age_seconds = (frappe.utils.now_datetime() - frappe.utils.get_datetime(existing_creation)).total_seconds()
				if age_seconds < 900:
					is_fresh = True

			if is_fresh:
				try:
					live_info = get_payment_status(existing_name)
					live_status = (live_info.get("status") or "").upper()
					if live_status == "INITIATED":
						return {
							"payment_url": existing[0]["payment_url"],
							"docname": existing_name,
							"company": company,
							"is_new": False,
						}
					elif live_status in ["SUCCESS", "ACCEPTED"]:
						_mark_paid(existing_name)
						return {
							"status": "Payé",
							"already_paid": True,
							"docname": existing_name,
							"company": company,
						}
					else:
						# FAILED, CANCELLED, REFUSED, etc.
						frappe.db.set_value("Subscription Payment", existing_name, "status", "Échoué")
						frappe.db.commit()
				except Exception:
					pass
			else:
				frappe.db.set_value("Subscription Payment", existing_name, "status", "Échoué")
				frappe.db.commit()

	# Create a brand new pending payment and generate a fresh CinetPay checkout session
	doc = frappe.get_doc({
		"doctype": "Subscription Payment",
		"company": company,
		"amount": 15000,
		"duration_months": 1,
		"status": "En attente",
	})
	doc.insert(ignore_permissions=True)
	doc.reload()

	payment_url = doc.payment_url
	if not payment_url:
		res = _generate_payment_link(doc)
		payment_url = res.get("payment_url")

	return {
		"payment_url": payment_url,
		"docname": doc.name,
		"company": company,
		"is_new": True,
	}


@frappe.whitelist()
def check_pme_subscription_status(docname=None):
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Connexion requise."), frappe.PermissionError)

	if docname and frappe.db.exists("Subscription Payment", docname):
		doc = frappe.get_doc("Subscription Payment", docname)

		if doc.status == "En attente":
			try:
				live_info = get_payment_status(doc.name)
				live_status = (live_info.get("status") or "").upper()
				if live_status in ["SUCCESS", "ACCEPTED"]:
					_mark_paid(doc.name)
					doc.reload()
				elif live_status in ["FAILED", "CANCELLED", "REFUSED"]:
					doc.db_set("status", "Échoué")
					frappe.db.commit()
					doc.reload()
			except Exception:
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


@frappe.whitelist(allow_guest=True)
def cinetpay_subscription_webhook():
	data = frappe.local.form_dict or {}

	merchant_transaction_id = (
		data.get("docname")
		or data.get("cpm_order_id")
		or data.get("merchant_transaction_id")
	)

	cpm_trans_id = data.get("cpm_trans_id") or data.get("transaction_id")

	doc = None
	if merchant_transaction_id and frappe.db.exists("Subscription Payment", merchant_transaction_id):
		doc = frappe.get_doc("Subscription Payment", merchant_transaction_id)
	elif cpm_trans_id:
		name = frappe.db.get_value("Subscription Payment", {"transaction_id": cpm_trans_id}, "name")
		if name:
			doc = frappe.get_doc("Subscription Payment", name)

	if not doc:
		frappe.response["http_status_code"] = 200
		return {"status": "ignored"}

	received_token = data.get("token") or data.get("notify_token")
	if doc.notify_token and received_token:
		if not hmac.compare_digest(str(doc.notify_token), str(received_token)):
			frappe.log_error(
				title="Subscription Payment: notify_token invalide",
				message=f"{doc.name}: jeton recu invalide",
			)
			frappe.response["http_status_code"] = 403
			return {"status": "forbidden"}

	if doc.status == "Payé":
		frappe.response["http_status_code"] = 200
		return {"status": "already processed"}

	status_data = get_payment_status(doc.name)
	real_status = (status_data.get("status") or "").upper()

	if real_status in ["SUCCESS", "ACCEPTED"]:
		_mark_paid(doc.name)
	elif real_status in ["FAILED", "CANCELLED", "REFUSED"]:
		doc.db_set("status", "Échoué")
		frappe.db.commit()

	frappe.response["http_status_code"] = 200
	return {"status": "ok"}
