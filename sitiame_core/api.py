# Copyright (c) 2026, Sitiame Capital
# License: MIT

import re

import frappe
from frappe import _


def _make_abbr(company_name, company_sigle=None):
	base = (company_sigle or company_name or "CO").strip()
	letters = re.sub(r"[^A-Za-z0-9]", "", base).upper()
	abbr = letters[:5] or "CO"

	original = abbr
	suffix = 1
	while frappe.db.exists("Company", {"abbr": abbr}):
		suffix += 1
		abbr = (original[:4] + str(suffix))[:5]

	return abbr


def _default_country():
	# Frappe's standard seed data names this record "Ivory Coast" (English),
	# not "Côte d'Ivoire" -- confirmed by reading the actual tabCountry table.
	for candidate in ["Ivory Coast", "Cote d'Ivoire", "Côte d'Ivoire"]:
		if frappe.db.exists("Country", candidate):
			return candidate
	return frappe.db.get_value("Country", {"name": ["like", "%Ivo%"]}, "name")


@frappe.whitelist(allow_guest=True)
def register_company(
	contact_name,
	email,
	password,
	company_name,
	phone=None,
	company_sigle=None,
	company_tax_id=None,
	sector=None,
	rccm=None,
	address=None,
	city=None,
):
	email = (email or "").strip().lower()
	contact_name = (contact_name or "").strip()
	company_name = (company_name or "").strip()

	if not contact_name or not email or not password or not company_name:
		frappe.throw(_("Nom du responsable, email, mot de passe et nom de l'entreprise sont obligatoires."))

	if len(password) < 8:
		frappe.throw(_("Le mot de passe doit contenir au moins 8 caracteres."))

	if frappe.db.exists("User", email):
		frappe.throw(_("Un compte existe deja avec cet email."))

	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": company_name,
			"abbr": _make_abbr(company_name, company_sigle),
			"default_currency": "XOF",
			"country": _default_country(),
			"tax_id": company_tax_id,
		}
	)
	company.insert(ignore_permissions=True)

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": contact_name,
			"send_welcome_email": 0,
			"new_password": password,
			"phone": phone,
			"roles": [{"role": "System Manager"}],
		}
	)
	user.insert(ignore_permissions=True)

	frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": email,
			"allow": "Company",
			"for_value": company.name,
		}
	).insert(ignore_permissions=True)

	frappe.get_doc(
		{
			"doctype": "Company Signup",
			"contact_name": contact_name,
			"email": email,
			"phone": phone,
			"company": company.name,
			"company_sigle": company_sigle,
			"sector": sector,
			"rccm": rccm,
			"trial_ends_on": frappe.utils.add_days(frappe.utils.today(), 30),
			"address": address,
			"city": city,
		}
	).insert(ignore_permissions=True)

	frappe.db.commit()

	frappe.local.login_manager.login_as(email)

	return {"success": True, "redirect": "/app"}
