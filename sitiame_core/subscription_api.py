# Copyright (c) 2026, Sitiame Capital
# License: MIT

import hmac

import requests

import frappe
from frappe import _

from sitiame_core.cinetpay_client import get_payment_status, init_payment


@frappe.whitelist()
def generate_subscription_payment_link(docname):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Reserve aux administrateurs."), frappe.PermissionError)

	doc = frappe.get_doc("Subscription Payment", docname)
	if doc.transaction_id:
		frappe.throw(_("Un lien de paiement a deja ete genere pour ce document."))

	site_url = frappe.utils.get_url()
	notify_url = f"{site_url}/api/method/sitiame_core.subscription_api.cinetpay_subscription_webhook"
	return_url = f"{site_url}/app/subscription-payment/{doc.name}"

	result = init_payment(
		merchant_transaction_id=doc.name,
		amount=doc.amount,
		designation=f"Abonnement premium Sitiame - {doc.company}",
		notify_url=notify_url,
		success_url=return_url,
		failed_url=return_url,
	)

	doc.db_set("transaction_id", result.get("transaction_id"))
	doc.db_set("notify_token", result.get("notify_token"))
	doc.db_set("payment_url", result.get("payment_url"))
	frappe.db.commit()

	return {"payment_url": result.get("payment_url")}


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
	real_status = status_data.get("status")

	if real_status == "SUCCESS":
		doc.db_set("status", "Payé")
		doc.db_set("paid_at", frappe.utils.now())
		frappe.db.commit()
		doc.reload()
		_notify_pme360(doc)
	elif real_status == "FAILED":
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
