# -*- coding: utf-8 -*-
# Copyright (c) 2026, Sitiame Capital
# License: MIT

import hmac

import requests

import frappe
from frappe import _

from sitiame_core.cinetpay_client import get_payment_status, init_payment


def _generate_payment_link(doc):
	site_url = frappe.utils.get_url()
	notify_url = f"{site_url}/api/method/sitiame_core.subscription_api.cinetpay_subscription_webhook"
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
	doc.db_set("notify_token", result.get("notify_token"))
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

	roles = frappe.get_roles()

	company = None
	if "System Manager" in roles:
		company = frappe.defaults.get_user_default("Company")
		if not company or company == "SITIAME":
			company = frappe.db.get_value("Company", {"name": ["!=", "SITIAME"]}, "name") or "SITIAME"
	else:
		company = frappe.db.get_value("User Permission", {"user": user, "allow": "Company"}, "for_value")
		if not company:
			company = frappe.defaults.get_user_default("Company")

	if not company:
		frappe.throw(_("Aucune societe rattachee a votre compte."))

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
						frappe.db.set_value("Subscription Payment", existing_name, "status", "Payé")
						frappe.db.set_value("Subscription Payment", existing_name, "paid_at", frappe.utils.now())
						frappe.db.commit()
						doc_paid = frappe.get_doc("Subscription Payment", existing_name)
						_notify_pme360(doc_paid)
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
					doc.db_set("status", "Payé")
					doc.db_set("paid_at", frappe.utils.now())
					frappe.db.commit()
					doc.reload()
					_notify_pme360(doc)
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
		}

	company = frappe.db.get_value("User Permission", {"user": user, "allow": "Company"}, "for_value") or frappe.defaults.get_user_default("Company")
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


def _notify_pme360(subscription_payment):
	base_url = (frappe.conf.get("pme360_base_url") or "https://sitiame-capital.com").rstrip("/")
	token = frappe.conf.get("pme360_webhook_token")
	if not token:
		frappe.log_error(
			title="Subscription Payment: pme360_webhook_token manquant",
			message=f"Impossible de notifier PME360 pour {subscription_payment.name}",
		)
		return False

	payload = {
		"company": subscription_payment.company,
		"duration_months": subscription_payment.duration_months,
		"paid_at": str(subscription_payment.paid_at),
	}
	try:
		response = requests.post(
			f"{base_url}/webhooks/erpnext/subscription-paid",
			json=payload,
			headers={"X-PME360-Webhook-Token": token},
			timeout=5,
		)
	except requests.RequestException as e:
		frappe.log_error(
			title="Subscription Payment: PME360 injoignable",
			message=f"{subscription_payment.name}: {e}",
		)
		return False

	if response.status_code >= 400:
		frappe.log_error(
			title="Subscription Payment: PME360 a refuse la notification",
			message=f"{subscription_payment.name}: {response.status_code} {response.text}",
		)
		return False

	frappe.db.set_value("Subscription Payment", subscription_payment.name, "pme360_notified_at", frappe.utils.now())
	frappe.db.commit()
	return True


@frappe.whitelist(allow_guest=True)
def cinetpay_subscription_webhook():
	data = frappe.local.form_dict
	merchant_transaction_id = data.get("merchant_transaction_id")
	notify_token = data.get("notify_token")

	if not merchant_transaction_id or not frappe.db.exists("Subscription Payment", merchant_transaction_id):
		frappe.response["http_status_code"] = 200
		return {"status": "ignored"}

	doc = frappe.get_doc("Subscription Payment", merchant_transaction_id)

	if not doc.notify_token or not notify_token or not hmac.compare_digest(str(doc.notify_token), str(notify_token)):
		frappe.response["http_status_code"] = 403
		frappe.log_error(
			title="Subscription Payment: notify_token invalide",
			message=f"{doc.name}: jeton recu invalide",
		)
		return {"status": "forbidden"}

	if doc.status == "Payé":
		frappe.response["http_status_code"] = 200
		return {"status": "already processed"}

	status_data = get_payment_status(merchant_transaction_id)
	real_status = (status_data.get("status") or "").upper()

	if real_status in ["SUCCESS", "ACCEPTED"]:
		doc.db_set("status", "Payé")
		doc.db_set("paid_at", frappe.utils.now())
		frappe.db.commit()
		doc.reload()
		_notify_pme360(doc)
	elif real_status in ["FAILED", "CANCELLED", "REFUSED"]:
		doc.db_set("status", "Échoué")
		frappe.db.commit()

	frappe.response["http_status_code"] = 200
	return {"status": "ok"}


@frappe.whitelist()
def resend_pme360_notification(docname):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Reserve aux administrateurs."), frappe.PermissionError)

	doc = frappe.get_doc("Subscription Payment", docname)
	if doc.status != "Payé":
		frappe.throw(_("Ce document n'est pas marque comme paye."))

	sent = _notify_pme360(doc)
	if not sent:
		frappe.throw(_("PME360 injoignable, voir le journal des erreurs (Error Log)."))

	return {"status": "ok"}
