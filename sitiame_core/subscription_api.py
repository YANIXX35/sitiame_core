# -*- coding: utf-8 -*-
# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""PME subscription to Sitiame (15 000 FCFA / month), independent of the
payment provider: state of a company's subscription, extension once a
payment is confirmed, staff overview.

The payment provider (Jèko) plugs in through _mark_paid, the single entry
point for a confirmed payment."""

import frappe
from frappe import _
from frappe.utils import add_months, getdate, today

from sitiame_core import portfolio
from sitiame_core.roles import CHARGE_AFFAIRES_ROLE
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
	"""Single entry point once the payment provider confirms a payment:
	flags the Subscription Payment as paid, extends the Company's
	subscription and gives back any access the trial expiry had removed.
	Row-locked so two confirmations racing each other (webhook, return
	page) can never extend the subscription twice."""
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
			# a payment webhook runs as Guest
			user.flags.ignore_permissions = True
			user.add_roles(*TRIAL_ROLES)
		frappe.db.set_value("Company Signup", signup.name, "trial_blocked", 0)


@frappe.whitelist()
def get_my_subscription():
	if frappe.session.user == "Guest":
		frappe.throw(_("Connexion requise."), frappe.PermissionError)
	return get_company_subscription(get_user_company())


@frappe.whitelist()
def list_company_subscriptions():
	"""Sitiame staff overview: every PME company with its subscription state
	and paid history (a chargé d'affaires: his portfolio)."""
	frappe.only_for(("System Manager", CHARGE_AFFAIRES_ROLE))

	paid = {}
	for row in frappe.get_all(
		"Subscription Payment", filters={"status": "Payé"}, fields=["company", "paid_at"]
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


@frappe.whitelist()
def check_pme_subscription_status(docname=None):
	"""A payment's recorded status (or the company's latest one) and the
	resulting subscription state."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Connexion requise."), frappe.PermissionError)

	if docname and frappe.db.exists("Subscription Payment", docname):
		doc = frappe.get_doc("Subscription Payment", docname)
		# a PME may only look at its own company's payments (amount, link)
		if "System Manager" not in frappe.get_roles() and doc.company != get_user_company(user):
			frappe.throw(_("Ce paiement ne concerne pas votre societe."), frappe.PermissionError)
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
