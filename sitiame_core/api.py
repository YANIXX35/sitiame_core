# Copyright (c) 2026, Sitiame Capital
# License: MIT

import json
import os
import random
import re
import shutil
import sys
import time
from datetime import datetime

import requests

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import flt, get_backups_path, get_bench_path

# Signup anti-bot: short-lived math challenge, answer cached server-side
# keyed by a one-time token. No external captcha service/API key needed.
_SIGNUP_CAPTCHA_CACHE_PREFIX = "sitiame_core:signup_captcha:"
_SIGNUP_CAPTCHA_TTL = 600  # 10 minutes


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=20, seconds=3600)
def get_signup_captcha():
	a = random.randint(2, 9)
	b = random.randint(2, 9)
	token = frappe.generate_hash(length=20)
	frappe.cache().set_value(
		_SIGNUP_CAPTCHA_CACHE_PREFIX + token, a + b, expires_in_sec=_SIGNUP_CAPTCHA_TTL
	)
	return {"token": token, "question": f"Combien font {a} + {b} ?"}


def _verify_signup_captcha(token, answer):
	token = (token or "").strip()
	if not token:
		frappe.throw(_("Verification anti-robot manquante."))

	cache_key = _SIGNUP_CAPTCHA_CACHE_PREFIX + token
	expected = frappe.cache().get_value(cache_key)
	# One-time use: consume immediately regardless of outcome.
	frappe.cache().delete_value(cache_key)

	if expected is None:
		frappe.throw(_("Verification anti-robot expiree, veuillez reessayer."))

	try:
		answer = int(str(answer).strip())
	except (TypeError, ValueError):
		answer = None

	if answer != expected:
		frappe.throw(_("Reponse incorrecte a la verification anti-robot."))

# Same provider/account PME360 already uses for its own OCR pipeline
# (app/Services/OcrService.php) -- reused here instead of standing up a
# second OCR integration.
OCR_SPACE_API_KEY = "K87899142C88957"
OCR_SPACE_ENDPOINT = "https://api.ocr.space/parse/image"


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


# Audit finding F-13: signups were getting ERPNext's generic "Standard" chart
# (95 unnumbered accounts) instead of SYSCOHADA -- broken for any accounting
# feature. F-11/F-12: default accounts and TVA templates weren't wired to
# the right accounts either. This mirrors the manual fix applied to SITIAME.
SYSCOHADA_CHART_OF_ACCOUNTS = "Syscohada - Plan Comptable avec code"

# account_number -> Company field to point at it once the chart exists.
_SYSCOHADA_DEFAULT_ACCOUNTS = {
	"4111": "default_receivable_account",
	"4011": "default_payable_account",
	"5211": "default_bank_account",
	"5711": "default_cash_account",
}

# account_number -> account_type to enforce (the SYSCOHADA template ships
# these untyped, which breaks TVA reporting and the Cash/Bank dashboards).
_SYSCOHADA_ACCOUNT_TYPES = {
	"4431": "Tax",
	"4432": "Tax",
	"4452": "Tax",
	"4454": "Tax",
	"5711": "Cash",
}


def _apply_syscohada_defaults(company_name):
	accounts_by_number = {
		row.account_number: row.name
		for row in frappe.get_all(
			"Account",
			filters={"company": company_name, "account_number": ["in", list(_SYSCOHADA_ACCOUNT_TYPES.keys() | _SYSCOHADA_DEFAULT_ACCOUNTS.keys())]},
			fields=["name", "account_number"],
		)
	}

	for number, account_type in _SYSCOHADA_ACCOUNT_TYPES.items():
		account_name = accounts_by_number.get(number)
		if account_name:
			frappe.db.set_value("Account", account_name, "account_type", account_type)

	company_updates = {}
	for number, fieldname in _SYSCOHADA_DEFAULT_ACCOUNTS.items():
		account_name = accounts_by_number.get(number)
		if account_name:
			company_updates[fieldname] = account_name

	if company_updates:
		frappe.db.set_value("Company", company_name, company_updates)


# Same 11-module allowlist as PME360's provisioning path
# (ErpNextClient::hiddenDesktopIconLabelsForPme) -- these are the DocType's
# raw `label` values as stored, not the French display text (every native
# ERPNext tile's label is still the untranslated English name; only the
# /desk display goes through __() at render time).
_PME_ALLOWED_DESKTOP_ICON_LABELS = [
	"Financement", "Scoring", "Selling", "Buying", "Stock",
	"Accounting", "Subcontracting", "Abonnement",
	"Manufacturing", "Projects", "Assets",
]


def _hidden_desktop_icon_labels_for_pme():
	all_labels = frappe.get_all("Desktop Icon", pluck="label")
	return [label for label in all_labels if label not in _PME_ALLOWED_DESKTOP_ICON_LABELS]


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=5, seconds=3600)
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
	captcha_token=None,
	captcha_answer=None,
	terms_accepted=None,
	# Honeypot: a field real visitors never see or fill (hidden via CSS on
	# the form). Any non-empty value here is a near-certain bot submission.
	website=None,
):
	if (website or "").strip():
		# Don't tip off the bot -- fail generically instead of a specific message.
		frappe.throw(_("Impossible de creer le compte."))

	_verify_signup_captcha(captcha_token, captcha_answer)

	if not frappe.utils.cint(terms_accepted):
		frappe.throw(_("Vous devez accepter les conditions d'utilisation et la politique de confidentialite."))

	email = (email or "").strip().lower()
	contact_name = (contact_name or "").strip()
	company_name = (company_name or "").strip()

	if not contact_name or not email or not password or not company_name:
		frappe.throw(_("Nom du responsable, email, mot de passe et nom de l'entreprise sont obligatoires."))

	if len(password) < 8:
		frappe.throw(_("Le mot de passe doit contenir au moins 8 caracteres."))

	if frappe.db.exists("User", email):
		frappe.throw(_("Un compte existe deja avec cet email."))

	# The Company Chart of Accounts import (SYSCOHADA, ~1370 accounts) alone
	# takes ~45s -- measured directly (2026-09-23) via bench-execute timing
	# scripts, not guessed. Doing that synchronously in the request meant the
	# form sat on "Creation en cours..." for ~48s total. The validation above
	# (captcha/honeypot/terms/email uniqueness) stays synchronous so bad
	# input still fails instantly; only the slow provisioning moves to a
	# background job. `token` is a random bearer credential (NOT the email)
	# so that polling status can also log the new user in once ready without
	# letting a third party who merely guesses/knows the email hijack the
	# session in the few-second window around completion.
	token = frappe.generate_hash(length=32)
	_set_company_signup_progress(token, {"status": "pending", "email": email})

	frappe.enqueue(
		"sitiame_core.api._provision_company_signup",
		queue="long",
		timeout=300,
		now=frappe.flags.in_test,
		token=token,
		contact_name=contact_name,
		email=email,
		password=password,
		company_name=company_name,
		phone=phone,
		company_sigle=company_sigle,
		company_tax_id=company_tax_id,
		sector=sector,
		rccm=rccm,
		address=address,
		city=city,
		signup_ip=frappe.local.request_ip,
	)

	return {"success": True, "pending": True, "token": token}


_COMPANY_SIGNUP_PROGRESS_PREFIX = "sitiame_core:company_signup_progress:"
_COMPANY_SIGNUP_PROGRESS_TTL = 900  # 15 minutes


def _set_company_signup_progress(token, data):
	frappe.cache().set_value(_COMPANY_SIGNUP_PROGRESS_PREFIX + token, data, expires_in_sec=_COMPANY_SIGNUP_PROGRESS_TTL)


def _get_company_signup_progress(token):
	return frappe.cache().get_value(_COMPANY_SIGNUP_PROGRESS_PREFIX + token)


def _provision_company_signup(
	token,
	contact_name,
	email,
	password,
	company_name,
	phone,
	company_sigle,
	company_tax_id,
	sector,
	rccm,
	address,
	city,
	signup_ip,
):
	# Background workers don't inherit the request's language the way a web
	# request does, so frappe.local.lang defaults to "en" here even though
	# the site's default (System Settings) is "fr". That mismatch is a real
	# bug: erpnext.setup.doctype.company.company.create_default_departments()
	# checks whether the shared "All Departments" root exists via
	# frappe.db.exists("Department", _("All Departments")) -- an exists-by-
	# name check -- while every child Department's parent_department link is
	# also set to that same literal _("All Departments") string. Under "en"
	# this string stays untranslated ("All Departments"), which matches
	# neither the real root (named "Tous les departements", created under
	# "fr" by earlier real web-request signups) nor any doc's actual name,
	# so every child Department insert fails with LinkValidationError and
	# the new company silently ends up with zero departments. Forcing "fr"
	# here (root-caused via a real reproduction on 2026-09-23, not guessed)
	# restores the same language context the old synchronous, in-request
	# code path always had.
	frappe.local.lang = "fr"
	try:
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": company_name,
				"abbr": _make_abbr(company_name, company_sigle),
				"default_currency": "XOF",
				"country": _default_country(),
				"tax_id": company_tax_id,
				"chart_of_accounts": SYSCOHADA_CHART_OF_ACCOUNTS,
				"create_chart_of_accounts_based_on": "Standard Template",
			}
		)
		company.insert(ignore_permissions=True)
		_apply_syscohada_defaults(company.name)

		# Same 11-tile allowlist and "PME Client" read-only dossier access as
		# the PME360-triggered signup path (ErpNextClient::provisionCompanyForPme,
		# see 2026-09-23-pme-erpnext-accounts-design.md) -- this form is a
		# second, independent entry point for the same kind of account and must
		# not diverge from it.
		hidden_desktop_icons = _hidden_desktop_icon_labels_for_pme()

		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": contact_name,
				"send_welcome_email": 0,
				"new_password": password,
				"phone": phone,
				# Deliberately NOT "System Manager": that role bypasses block_modules
				# (Frappe treats it as admin-equivalent for the trial-blocking check
				# in desk.py), which would make the 1-month trial cutoff a no-op.
				# Full list verified against each module's real DocPerm requirements
				# (2026-09-23): Frappe roles are not hierarchical, so "Manager"
				# alone does not imply "User" -- e.g. Work Order's create perm is
				# granted to "Manufacturing User", not "Manufacturing Manager", and
				# Project/Task need "Projects User" specifically. Organisation/Club
				# Sportif carry no ERPNext business role at all and stay excluded
				# (Sitiame-internal/admin-only).
				"roles": [
					{"role": "PME Client"},
					{"role": "Accounts Manager"},
					{"role": "Accounts User"},
					{"role": "Sales Manager"},
					{"role": "Sales User"},
					{"role": "Purchase Manager"},
					{"role": "Purchase Master Manager"},
					{"role": "Purchase User"},
					{"role": "Stock Manager"},
					{"role": "Stock User"},
					{"role": "Item Manager"},
					{"role": "Manufacturing Manager"},
					{"role": "Manufacturing User"},
					{"role": "Projects Manager"},
					{"role": "Projects User"},
					{"role": "Quality Manager"},
				],
				"sitiame_hidden_desktop_icons": json.dumps(hidden_desktop_icons),
				"sitiame_hidden_sidebar_items": json.dumps(["erp-financial-ranking", "Scoring 360 Settings"]),
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
				"terms_accepted": 1,
				"terms_accepted_at": frappe.utils.now_datetime(),
				"signup_ip": signup_ip,
			}
		).insert(ignore_permissions=True)

		frappe.db.commit()
		_set_company_signup_progress(token, {"status": "success", "email": email})
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Company signup provisioning failed", message=frappe.get_traceback())
		_set_company_signup_progress(
			token,
			{
				"status": "failed",
				"email": email,
				"message": _(
					"La creation de votre compte a echoue. Veuillez reessayer ou nous contacter."
				),
			},
		)


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=3600)
def get_company_signup_status(token):
	progress = _get_company_signup_progress(token)
	if not progress:
		return {"status": "not_found"}

	if progress["status"] == "success":
		frappe.local.login_manager.login_as(progress["email"])
		frappe.cache().delete_value(_COMPANY_SIGNUP_PROGRESS_PREFIX + token)
		return {"status": "success", "redirect": "/app"}

	if progress["status"] == "failed":
		frappe.cache().delete_value(_COMPANY_SIGNUP_PROGRESS_PREFIX + token)
		return {"status": "failed", "message": progress.get("message")}

	return {"status": "pending"}


# Invoice-scan extraction: pulls raw text via OCR.space, then runs a
# label-based structured extraction pass on top of it (see
# _extract_invoice_fields below) so the caller gets named, normalised
# fields instead of just raw text. Deliberately not a port of PME360's
# full field-by-field extraction pipeline (app/Services/OcrService.php)
# -- this is a regex/label matcher, not an ML document parser.
#
# Hard rule enforced throughout this section: a field is only ever set
# when a matching label is actually found in the OCR text. Nothing here
# infers, calculates, or defaults a business value that wasn't printed
# on the document.
_AMOUNT_PATTERN = re.compile(
	r"(?:TOTAL|MONTANT|NET\s*A\s*PAYER)[^\d]{0,20}([\d][\d\s.,]{2,})", re.IGNORECASE
)
_DATE_PATTERN = re.compile(r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}-\d{1,2}-\d{1,2})\b")
_CLIENT_PATTERN = re.compile(r"(?:Client|Fournisseur)\s*[:\-]\s*(.+)", re.IGNORECASE)

_AMOUNT_VALUE = r"([\d][\d\s.,]{2,})"
_DATE_VALUE = r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}-\d{1,2}-\d{1,2})"

_INVOICE_NUMBER_PATTERNS = [
	re.compile(
		r"(?:Facture\s*N[°ºo]?|N[°ºo]?\s*(?:de\s*)?[Ff]acture|Num[eé]ro\s*(?:de\s*)?facture)"
		r"\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/_.]{2,})",
		re.IGNORECASE,
	),
	# A standalone "N° <value>" / "No <value>" line, for layouts where
	# "FACTURE" is its own heading line and the number follows on the next
	# line without repeating the word "Facture" (common OCR output). The
	# caller additionally requires the captured value to contain a digit
	# (see _looks_like_reference below), so this can't mis-fire on an
	# unrelated "N° Contribuable" / "N° RCCM" line that has no separator
	# right after "N°".
	re.compile(r"^\s*N[°ºo]\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/_.]{2,})\s*$", re.IGNORECASE | re.MULTILINE),
]
_INVOICE_DATE_PATTERNS = [
	# "Date de facture", "Date d'emission", "Date de reception", "Date de
	# livraison", ... -- any "Date (de|d') <word>" label, as long as that
	# word isn't "echeance" (that's due_date's own pattern below), plus the
	# bare "Date :" form.
	re.compile(
		r"Date\s*(?:d[e’']\s*(?!\s*[ée]ch[ée]ance)[A-Za-zÀ-ÿ]+\s*)?[:\-]\s*" + _DATE_VALUE,
		re.IGNORECASE,
	),
]
_DUE_DATE_PATTERNS = [
	re.compile(
		r"(?:[ÉE]ch[ée]ance|Date\s*d[’']?[ée]ch[ée]ance)\s*[:\-]?\s*" + _DATE_VALUE,
		re.IGNORECASE,
	),
]
_SUPPLIER_PATTERNS = [re.compile(r"Fournisseur\s*[:\-]\s*(.+)", re.IGNORECASE)]
_CUSTOMER_PATTERNS = [re.compile(r"Client\s*[:\-]\s*(.+)", re.IGNORECASE)]
_TAX_ID_PATTERNS = [
	re.compile(r"\bNIF\s*[:\-]?\s*([A-Za-z0-9\-]{4,})", re.IGNORECASE),
	re.compile(r"N[°ºo]?\s*Contribuable\s*[:\-]?\s*([A-Za-z0-9\-]{4,})", re.IGNORECASE),
	# NCC (Numero de Compte Contribuable) is the standard Ivorian tax id
	# label, at least as common on real invoices as "NIF".
	re.compile(r"\bNCC\s*[:\-]?\s*([A-Za-z0-9\-]{4,})", re.IGNORECASE),
]
_SUBTOTAL_PATTERNS = [
	re.compile(r"(?:TOTAL|MONTANT)\s*H\.?T\.?\s*[:\-]?\s*" + _AMOUNT_VALUE, re.IGNORECASE),
]
_TAX_AMOUNT_PATTERNS = [
	# The rate suffix is optional and may appear bare ("TVA 18% :") or
	# parenthesised ("TVA (18%) :") -- both seen on real invoices.
	re.compile(r"T\.?V\.?A\.?(?:\s*\(?\d{1,2}\s*%\)?)?\s*[:\-]?\s*" + _AMOUNT_VALUE, re.IGNORECASE),
]
_GRAND_TOTAL_PATTERNS = [
	re.compile(r"(?:TOTAL|MONTANT)\s*T\.?T\.?C\.?\s*[:\-]?\s*" + _AMOUNT_VALUE, re.IGNORECASE),
	re.compile(r"NET\s*A\s*PAYER\s*[:\-]?\s*" + _AMOUNT_VALUE, re.IGNORECASE),
]


def _parse_amount(raw: str) -> float | None:
	cleaned = re.sub(r"[^\d,.]", "", raw or "")
	if not cleaned:
		return None

	if "," in cleaned and "." in cleaned:
		# Both separators present: whichever comes LAST is the decimal
		# point, the other is a thousands grouping -- e.g. "1.234.567,89"
		# (French/European) vs "1,234,567.89" (English).
		if cleaned.rfind(",") > cleaned.rfind("."):
			cleaned = cleaned.replace(".", "").replace(",", ".")
		else:
			cleaned = cleaned.replace(",", "")
	elif "," in cleaned or "." in cleaned:
		sep = "," if "," in cleaned else "."
		parts = cleaned.split(sep)
		# A single separator with exactly 3 digits after it is a thousands
		# grouping, not a decimal point -- FCFA amounts don't carry centimes
		# in practice, so "500.000" means 500000, not 500. A 1-2 digit tail
		# ("12.50") is a real decimal and is kept as one.
		if len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) >= 1:
			cleaned = cleaned.replace(sep, "")
		else:
			cleaned = cleaned.replace(sep, ".")

	try:
		return float(cleaned)
	except ValueError:
		return None


def _parse_date_token(raw: str) -> str | None:
	raw = (raw or "").strip()
	iso_match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", raw)
	if iso_match:
		year, month, day = iso_match.groups()
	else:
		for sep in ("/", "-", "."):
			if sep in raw:
				parts = raw.split(sep)
				break
		else:
			return None
		if len(parts) != 3:
			return None
		day, month, year = parts
		if len(year) == 2:
			year = "20" + year
	try:
		return frappe.utils.formatdate(f"{year}-{int(month):02d}-{int(day):02d}", "yyyy-mm-dd")
	except Exception:
		return None


def _best_guess_amount(text: str) -> float | None:
	matches = _AMOUNT_PATTERN.findall(text)
	amounts = [a for a in (_parse_amount(m) for m in matches) if a]
	return max(amounts) if amounts else None


def _best_guess_date(text: str) -> str | None:
	match = _DATE_PATTERN.search(text)
	return _parse_date_token(match.group(1)) if match else None


def _best_guess_client(text: str) -> str | None:
	match = _CLIENT_PATTERN.search(text)
	if not match:
		return None
	name = match.group(1).strip()
	return name or None


def _guess_supplier_from_letterhead(text: str) -> str | None:
	"""Last-resort supplier guess: many real invoices never write the word
	"Fournisseur" at all -- the issuer's name is only in the letterhead
	(the first line(s) of the document). Only used when the explicit
	"Fournisseur :" label isn't found, and always tagged with a low
	confidence score so the caller can flag it for review rather than
	treat it the same as a labelled match.
	"""
	for line in (text or "").splitlines():
		line = line.strip()
		if not line:
			continue
		# Skip the document-type heading itself ("FACTURE", "INVOICE", ...),
		# that's not a company name.
		if re.match(r"^(facture|invoice|devis|avoir|bon de commande)\b", line, re.IGNORECASE):
			continue
		return line[:120]
	return None


def _extract_invoice_fields(text: str) -> tuple[dict, dict]:
	"""Structured, label-based extraction on top of the raw OCR text.

	Returns (fields, confidence) -- a field is present in `fields` ONLY
	when a recognised label was actually matched in the text (with one
	explicit, clearly-flagged exception: supplier_name falls back to the
	document's letterhead at confidence 0.5 when no "Fournisseur :" label
	exists at all -- see _guess_supplier_from_letterhead). Nothing else is
	inferred or defaulted: an absent label means the key is simply not in
	the dict, and the caller must leave the corresponding form field
	untouched.
	"""
	fields: dict = {}
	confidence: dict = {}

	def add(key, patterns, normalizer=None, conf=0.9, validator=None):
		for pattern in patterns:
			match = pattern.search(text)
			if not match:
				continue
			raw = match.group(1).strip().strip(".,;")
			if validator and not validator(raw):
				continue
			value = normalizer(raw) if normalizer else raw
			if value not in (None, ""):
				fields[key] = value
				confidence[key] = conf
				return

	# A real invoice reference always contains at least one digit -- this
	# keeps the standalone "N° <value>" pattern above from mis-firing on
	# an unrelated "N° Contribuable"/"N° RCCM" line whose value is a word.
	def _looks_like_reference(raw):
		return any(ch.isdigit() for ch in raw)

	add("invoice_number", _INVOICE_NUMBER_PATTERNS, validator=_looks_like_reference)
	add("invoice_date", _INVOICE_DATE_PATTERNS, _parse_date_token)
	add("due_date", _DUE_DATE_PATTERNS, _parse_date_token)
	add("supplier_name", _SUPPLIER_PATTERNS)
	if "supplier_name" not in fields:
		guess = _guess_supplier_from_letterhead(text)
		if guess:
			fields["supplier_name"] = guess
			confidence["supplier_name"] = 0.5
	add("customer_name", _CUSTOMER_PATTERNS)
	add("tax_id", _TAX_ID_PATTERNS)
	add("subtotal", _SUBTOTAL_PATTERNS, _parse_amount)
	add("tax_amount", _TAX_AMOUNT_PATTERNS, _parse_amount)
	add("grand_total", _GRAND_TOTAL_PATTERNS, _parse_amount)

	return fields, confidence


_SUMMARY_LINE_RE = re.compile(
	r"^\s*(nombre\s*total|total|sous[- ]total|montant\s*h\.?t\.?|tva|montant\s*t\.?t\.?c\.?)\b",
	re.IGNORECASE,
)


def _extract_line_items(text: str) -> list:
	"""Parse the item table (Designation/Reference/Qte/Unite, or
	Designation/Qte/Prix unitaire/Montant) into one dict per row.

	OCR.space's isTable mode keeps columns aligned with runs of spaces, so
	rows are split on 2+ consecutive spaces rather than a single space
	(item/reference names routinely contain single spaces). Only
	item_name and qty are ever handed to the caller to fill in -- unit,
	item code and rate would need to match an existing master record
	(UOM/Item) to be safe to set on a Link field, which this function has
	no way to verify, so it doesn't guess those.
	"""
	lines = (text or "").splitlines()
	header_idx = None
	header_cells: list = []
	for i, line in enumerate(lines):
		if re.match(r"^\s*d[ée]signation\b", line, re.IGNORECASE):
			header_idx = i
			header_cells = [c.strip().lower() for c in re.split(r"\s{2,}", line.strip()) if c.strip()]
			break
	if header_idx is None:
		return []

	def col_index(*keywords):
		for idx, cell in enumerate(header_cells):
			if any(kw in cell for kw in keywords):
				return idx
		return None

	qty_idx = col_index("qte", "qté", "quantite", "quantité")

	items = []
	for line in lines[header_idx + 1 :]:
		stripped = line.strip()
		if not stripped:
			break
		if _SUMMARY_LINE_RE.match(stripped):
			break
		cells = [c.strip() for c in re.split(r"\s{2,}", stripped) if c.strip()]
		if len(cells) < 2:
			break
		entry = {"item_name": cells[0]}
		if qty_idx is not None and qty_idx < len(cells):
			qty_value = _parse_amount(cells[qty_idx])
			if qty_value is not None:
				entry["qty"] = qty_value
		items.append(entry)

	return items


def _detect_document_type(text: str, fields: dict) -> str:
	lowered = (text or "").lower()
	if "facture" not in lowered and "invoice" not in lowered:
		if "devis" in lowered or "quotation" in lowered:
			return "quotation"
		if "avoir" in lowered or "credit note" in lowered:
			return "credit_note"
		if "bon de commande" in lowered or "purchase order" in lowered:
			return "purchase_order"
	if "facture" in lowered or "invoice" in lowered or fields:
		return "invoice"
	return "unknown"


@frappe.whitelist()
def ocr_extract_invoice(file_url):
	"""Send an already-uploaded file (PDF/image) to OCR.space, then run the
	structured extraction pass on the resulting text.

	Uploaded files are private by default, so OCR.space can't fetch them
	back over the "url" param (it isn't authenticated against this site) --
	the file bytes are read locally and posted directly instead.

	Response shape (fields/confidence/document_type are new; text/amount/
	date/client_name are kept unchanged for backwards compatibility with
	any doctype that only used the old best-effort behaviour):
		{
			"text": "...",
			"amount": 590000.0,            # legacy best-guess, unchanged
			"date": "2026-09-15",          # legacy best-guess, unchanged
			"client_name": "ABC SARL",     # legacy best-guess, unchanged
			"document_type": "invoice",
			"fields": {"invoice_number": "FAC-2026-00125", ...},
			"confidence": {"invoice_number": 0.9, ...},
		}
	"""
	filename, content = frappe.utils.file_manager.get_file(file_url)

	response = requests.post(
		OCR_SPACE_ENDPOINT,
		data={
			"apikey": OCR_SPACE_API_KEY,
			"language": "fre",
			"OCREngine": 2,
			"isTable": "true",
			"scale": "true",
			"detectOrientation": "true",
		},
		files={"file": (filename, content)},
		timeout=60,
	)
	result = response.json()

	if result.get("IsErroredOnProcessing"):
		frappe.throw(_("Echec de la lecture du document : {0}").format(result.get("ErrorMessage")))

	parsed = result.get("ParsedResults") or []
	text = "\n".join(p.get("ParsedText", "") for p in parsed).strip()

	fields, confidence = _extract_invoice_fields(text)
	document_type = _detect_document_type(text, fields)
	line_items = _extract_line_items(text)

	frappe.logger("sitiame_core.ocr").info(
		f"[OCR] document_type={document_type} fields={fields} confidence={confidence} "
		f"line_items={line_items}"
	)

	return {
		"text": text,
		"amount": _best_guess_amount(text),
		"date": _best_guess_date(text),
		"client_name": _best_guess_client(text),
		"document_type": document_type,
		"fields": fields,
		"confidence": confidence,
		"line_items": line_items,
	}


# ERPNext database backups, listed/managed from the "Sauvegardes ERPNext"
# page (Users workspace, System Manager only) -- mirrors PME360's own
# /admin/backups feature so the ERP site has the same safety net.
_BACKUP_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(sql\.gz|sql|tar)$")


def _safe_backup_path(filename):
	filename = os.path.basename(filename or "")
	if not _BACKUP_FILENAME_RE.match(filename):
		frappe.throw(_("Nom de fichier invalide."))

	path = os.path.join(get_backups_path(), filename)
	if not os.path.isfile(path):
		frappe.throw(_("Sauvegarde introuvable."), frappe.DoesNotExistError)

	return path


@frappe.whitelist()
def list_erp_backups():
	frappe.only_for("System Manager")

	backups_dir = get_backups_path()
	if not os.path.isdir(backups_dir):
		return []

	rows = []
	for fname in os.listdir(backups_dir):
		if not fname.endswith((".sql.gz", ".sql")):
			continue
		full_path = os.path.join(backups_dir, fname)
		stat = os.stat(full_path)
		rows.append(
			{
				"filename": fname,
				"size_mb": round(stat.st_size / 1024 / 1024, 2),
				"modified": stat.st_mtime,
				"created_at": frappe.utils.format_datetime(datetime.fromtimestamp(stat.st_mtime), "dd-MM-yyyy HH:mm"),
			}
		)

	rows.sort(key=lambda r: r["modified"], reverse=True)
	for row in rows:
		del row["modified"]

	return rows


@frappe.whitelist()
def run_erp_backup_now():
	frappe.only_for("System Manager")

	from frappe.utils.backups import new_backup

	backup = new_backup(ignore_files=True)
	return {"filename": os.path.basename(backup.backup_path_db)}


@frappe.whitelist()
def delete_erp_backup(filename):
	frappe.only_for("System Manager")
	os.remove(_safe_backup_path(filename))


@frappe.whitelist(methods=["GET"])
def download_erp_backup(filename):
	frappe.only_for("System Manager")

	path = _safe_backup_path(filename)
	with open(path, "rb") as f:
		frappe.local.response.filename = os.path.basename(path)
		frappe.local.response.filecontent = f.read()
		frappe.local.response.type = "download"


# ERPNext health/incident dashboard, shown on the "Signalements ERPNext"
# page (Organisation sidebar, System Manager only) -- mirrors PME360's own
# /admin/signalements page, but built on Frappe's own native equivalents
# instead of a parallel bug-tracking table: "Error Log" (every unhandled
# server exception is already captured there automatically) and
# "Activity Log" (already records every Login/Logout with a status).
_APP_LOG_PATH = os.path.join(get_bench_path(), "logs", "frappe.log")


def _tail_file(path, max_lines=150):
	if not os.path.isfile(path):
		return _("Aucun fichier de log trouve.")

	with open(path, "r", errors="replace") as f:
		lines = f.readlines()

	if not lines:
		return _("Le fichier de log est vide (aucun incident recent).")

	return "".join(lines[-max_lines:])


@frappe.whitelist()
def get_erp_health_dashboard():
	frappe.only_for("System Manager")

	recent_errors = frappe.get_all(
		"Error Log",
		fields=["name", "method", "creation", "seen"],
		order_by="creation desc",
		limit=15,
	)

	db_error = None
	table_count = 0
	started = time.time()
	try:
		table_count = len(frappe.db.sql("SHOW TABLES"))
		db_connected = True
	except Exception as e:
		db_connected = False
		db_error = str(e)
	ping_ms = round((time.time() - started) * 1000, 2)

	disk_total, _used, disk_free = shutil.disk_usage(get_bench_path())

	recent_logins = frappe.get_all(
		"Activity Log",
		filters={"operation": ["in", ["Login", "Logout"]]},
		fields=["user", "operation", "status", "creation"],
		order_by="creation desc",
		limit=20,
	)

	return {
		"errors": {
			"open": frappe.db.count("Error Log", {"seen": 0}),
			"total": frappe.db.count("Error Log"),
			"recent": recent_errors,
		},
		"db": {
			"connected": db_connected,
			"table_count": table_count,
			"ping_ms": ping_ms,
			"error": db_error,
		},
		"server": {
			"python_version": sys.version.split()[0],
			"disk_free_gb": round(disk_free / 1024**3, 2),
			"disk_total_gb": round(disk_total / 1024**3, 2),
		},
		"logins": {
			"recent": recent_logins,
			"total_success": frappe.db.count("Activity Log", {"operation": "Login", "status": "Success"}),
			"total_failed": frappe.db.count("Activity Log", {"operation": "Login", "status": "Failed"}),
		},
		"log_tail": _tail_file(_APP_LOG_PATH),
	}


@frappe.whitelist()
def mark_error_log_seen(name):
	frappe.only_for("System Manager")
	frappe.db.set_value("Error Log", name, "seen", 1)
	frappe.db.commit()


@frappe.whitelist()
def clear_erp_logs():
	"""Mirrors PME360's 'Vider les logs' action: empties the app log file
	and removes already-reviewed Error Log entries older than 7 days."""
	frappe.only_for("System Manager")

	if os.path.isfile(_APP_LOG_PATH):
		open(_APP_LOG_PATH, "w").close()

	week_ago = frappe.utils.add_days(frappe.utils.now(), -7)
	old_seen = frappe.get_all("Error Log", filters={"seen": 1, "creation": ["<", week_ago]}, pluck="name")
	for name in old_seen:
		frappe.delete_doc("Error Log", name, ignore_permissions=True, force=True)

	frappe.db.commit()
	return {"cleared_errors": len(old_seen)}


@frappe.whitelist()
def get_financial_ranking(date_from=None, date_to=None):
	"""Ranks every ERPNext Company by its Scoring 360 Composite score/
	decision (pret_a_deployer/solide_mais_a_cadrer/risque_a_traiter/
	insuffisant). See scoring360_service.py::classement_erpnext."""
	frappe.only_for("System Manager")

	from sitiame_core.scoring360_service import classement_erpnext

	return classement_erpnext(date_from or None, date_to or None)


@frappe.whitelist()
def get_scoring360_score(company, date_from=None, date_to=None):
	"""ERPNext port of PME360's Scoring360Service::scoreUser(), driven by
	the "Scoring 360 Settings" single doctype. See scoring360_service.py."""
	frappe.only_for("System Manager")

	from sitiame_core.scoring360_service import score_company

	return score_company(company, date_from or None, date_to or None)


@frappe.whitelist()
def list_erp_payments(company=None, party=None, status=None, mode_of_payment=None, date_from=None, date_to=None):
	"""Real ERPNext payments (Payment Entry), shown on the "Paiements ERPNext"
	page (Organisation sidebar). Unlike PME360's /admin/payments (which
	tracks PME360's own Premium-subscription mobile-money transactions --
	no ERPNext equivalent exists), this reflects each Company's actual
	customer/supplier payments."""
	frappe.only_for("System Manager")

	filters = {"docstatus": ["!=", 2]}
	if company:
		filters["company"] = company
	if party:
		filters["party"] = ["like", f"%{party}%"]
	if status:
		filters["status"] = status
	if mode_of_payment:
		filters["mode_of_payment"] = mode_of_payment
	if date_from and date_to:
		filters["posting_date"] = ["between", [date_from, date_to]]
	elif date_from:
		filters["posting_date"] = [">=", date_from]
	elif date_to:
		filters["posting_date"] = ["<=", date_to]

	rows = frappe.get_all(
		"Payment Entry",
		filters=filters,
		fields=[
			"name", "posting_date", "company", "payment_type", "party_type", "party",
			"party_name", "paid_amount", "received_amount", "paid_from_account_currency",
			"mode_of_payment", "reference_no", "reference_date", "status",
		],
		order_by="posting_date desc, creation desc",
		limit=200,
	)

	received_total = sum(flt(r.received_amount) for r in rows if r.payment_type == "Receive")
	paid_total = sum(flt(r.paid_amount) for r in rows if r.payment_type == "Pay")

	return {
		"rows": rows,
		"summary": {
			"count": len(rows),
			"received_total": received_total,
			"paid_total": paid_total,
		},
	}


@frappe.whitelist()
def list_erp_kyc_documents(company=None):
	"""KYC/KYB documents for each ERPNext Company, shown on the "Documents
	KYC ERPNext" page (Organisation sidebar). PME360 already pushes each
	client's approved KYC documents here (SyncKycDocumentsToErpNext job,
	app/Jobs/SyncKycDocumentsToErpNext.php), attaching them as private
	Files on the matching Company record -- this just surfaces what that
	sync produces, grouped by company, instead of opening each Company one
	by one to check its Attachments panel."""
	frappe.only_for("System Manager")

	filters = {"attached_to_doctype": "Company"}
	if company:
		filters["attached_to_name"] = company

	files = frappe.get_all(
		"File",
		filters=filters,
		fields=["name", "file_name", "file_url", "attached_to_name", "is_private", "file_size", "creation"],
		order_by="attached_to_name asc, creation desc",
	)

	companies = {c.name: c.company_name for c in frappe.get_all("Company", fields=["name", "company_name"])}

	groups = {}
	for f in files:
		key = f.attached_to_name
		groups.setdefault(
			key,
			{"company": key, "company_name": companies.get(key, key), "documents": []},
		)
		groups[key]["documents"].append(
			{
				"name": f.name,
				"file_name": f.file_name,
				"file_url": f.file_url,
				"size_kb": round((f.file_size or 0) / 1024, 1),
				"created_at": frappe.utils.format_datetime(f.creation, "dd-MM-yyyy HH:mm"),
			}
		)

	return {
		"groups": sorted(groups.values(), key=lambda g: g["company_name"]),
		"total_documents": len(files),
		"total_companies_with_documents": len(groups),
	}


# Status-mapping mirrors PME360's Caisse Banque page (unpaid/partial/paid),
# built from ERPNext's own "status" field on Sales/Purchase Invoice instead
# of a parallel AccountingEntry.payment_status column.
_INVOICE_STATUS_BUCKET = {
	"Unpaid": "unpaid",
	"Overdue": "unpaid",
	"Partly Paid": "partial",
	"Paid": "paid",
}


@frappe.whitelist()
def list_caisse_banque(bucket=None, document_type=None, date_from=None, date_to=None):
	"""ERPNext equivalent of PME360's Caisse Banque page: unpaid/partial/
	paid Sales & Purchase Invoices in one list, with totals per bucket.
	Respects the caller's normal doc permissions (frappe.get_list), so a
	company account only ever sees its own Company's invoices."""

	rows = []

	def _load(doctype, party_field, party_name_field):
		filters = {"docstatus": 1}
		if date_from and date_to:
			filters["posting_date"] = ["between", [date_from, date_to]]
		elif date_from:
			filters["posting_date"] = [">=", date_from]
		elif date_to:
			filters["posting_date"] = ["<=", date_to]

		for r in frappe.get_list(
			doctype,
			filters=filters,
			fields=["name", "posting_date", "company", party_field, party_name_field, "grand_total", "outstanding_amount", "status"],
			order_by="posting_date desc",
			limit_page_length=0,
		):
			b = _INVOICE_STATUS_BUCKET.get(r.status)
			if b is None:
				continue
			if bucket and b != bucket:
				continue
			rows.append(
				{
					"document_type": doctype,
					"name": r.name,
					"posting_date": r.posting_date,
					"company": r.company,
					"party_name": r.get(party_name_field) or r.get(party_field),
					"amount": r.grand_total,
					"outstanding": r.outstanding_amount,
					"bucket": b,
					"status": r.status,
				}
			)

	if not document_type or document_type == "Sales Invoice":
		_load("Sales Invoice", "customer", "customer_name")
	if not document_type or document_type == "Purchase Invoice":
		_load("Purchase Invoice", "supplier", "supplier_name")

	rows.sort(key=lambda r: r["posting_date"] or "", reverse=True)

	totals = {"unpaid": 0.0, "partial": 0.0, "paid": 0.0}
	for r in rows:
		amount = r["outstanding"] if r["bucket"] in ("unpaid", "partial") else r["amount"]
		totals[r["bucket"]] += flt(amount)

	return {"rows": rows, "totals": totals}


# ERPNext port of PME360's "Cloture mensuelle" (app/Http/Controllers/
# AccountingController.php::monthlyClosing/storeMonthClosure): a checklist
# + soft marker, not an enforced lock -- same scope as PME360's own
# version (its "cloture" doesn't block further postings either, it's a
# business bookmark saying the month was reviewed). ERPNext's own
# "Period Closing Voucher" is a real, consequential accounting entry and
# is deliberately NOT auto-triggered here.
@frappe.whitelist()
def get_month_closing_status(company, year_month):
	import re as _re

	if not _re.match(r"^\d{4}-\d{2}$", year_month or ""):
		frappe.throw(_("Mois invalide (format attendu : AAAA-MM)."))

	start = f"{year_month}-01"
	end = frappe.utils.get_last_day(start)

	entries_count = frappe.db.sql(
		"""select count(distinct concat(voucher_type, '||', voucher_no))
		from `tabGL Entry`
		where company=%(company)s and is_cancelled=0
			and posting_date between %(start)s and %(end)s""",
		{"company": company, "start": start, "end": end},
	)[0][0]

	payments_count = frappe.db.count(
		"Payment Entry",
		{"company": company, "docstatus": 1, "posting_date": ["between", [start, end]]},
	)

	closure = None
	name = f"{company}-{year_month}"
	if frappe.db.exists("ERP Month Closure", name):
		doc = frappe.get_doc("ERP Month Closure", name)
		closure = {
			"closed_at": doc.closed_at,
			"closed_by": doc.closed_by,
			"notes": doc.notes,
		}

	return {
		"year_month": year_month,
		"start": start,
		"end": end,
		"entries_count": entries_count,
		"payments_count": payments_count,
		"check_journal": entries_count > 0,
		"check_payments": payments_count > 0,
		"closure": closure,
	}


@frappe.whitelist()
def close_month(company, year_month, notes=None):
	import re as _re

	if not _re.match(r"^\d{4}-\d{2}$", year_month or ""):
		frappe.throw(_("Mois invalide (format attendu : AAAA-MM)."))

	name = f"{company}-{year_month}"
	if frappe.db.exists("ERP Month Closure", name):
		doc = frappe.get_doc("ERP Month Closure", name)
		doc.notes = notes
		doc.closed_at = frappe.utils.now()
		doc.closed_by = frappe.session.user
		doc.save()
	else:
		doc = frappe.get_doc(
			{
				"doctype": "ERP Month Closure",
				"company": company,
				"year_month": year_month,
				"notes": notes,
			}
		)
		doc.insert()

	frappe.db.commit()
	return {"name": doc.name, "closed_at": doc.closed_at}


# ERPNext port of PME360's "Assistant IA Admin" (Google Gemini). See
# gemini_assistant.py for the chat engine itself; context here is built
# from ERPNext data this app already exposes (backups, errors, financial
# ranking, payments) rather than PME360's own Ops Center/SLA data.
_ASSISTANT_ALLOWED_ROLES = ["System Manager", "Accounts Manager"]


def _build_assistant_context():
	open_errors = frappe.db.count("Error Log", {"seen": 0})
	failed_logins = frappe.db.count("Activity Log", {"operation": "Login", "status": "Failed"})

	try:
		from sitiame_core.scoring360_service import classement_erpnext

		ranking = classement_erpnext()
		compteurs = ranking.get("compteurs", {})
	except Exception:
		compteurs = {}

	unpaid_count = frappe.db.count("Sales Invoice", {"docstatus": 1, "status": ["in", ["Unpaid", "Overdue"]]})
	unpaid_count += frappe.db.count("Purchase Invoice", {"docstatus": 1, "status": ["in", ["Unpaid", "Overdue"]]})

	backups_dir = get_backups_path()
	backups_count = 0
	if os.path.isdir(backups_dir):
		backups_count = len([f for f in os.listdir(backups_dir) if f.endswith((".sql.gz", ".sql"))])

	companies = frappe.db.count("Company")

	return (
		"Tu es l'assistant IA administrateur d'une instance ERPNext pour Sitiame Capital "
		"(plateforme de gestion pour PME en Afrique de l'Ouest). Reponds en francais, de facon "
		"concise et actionnable, en te basant sur le contexte fourni. Ne donne jamais de conseil "
		"financier reglementaire formel -- tu es un outil d'aide a la decision interne.\n\n"
		"Contexte actuel de la plateforme ERPNext :\n"
		f"- {companies} societe(s) enregistree(s)\n"
		f"- {open_errors} erreur(s) systeme non vue(s) (Error Log)\n"
		f"- {failed_logins} tentative(s) de connexion echouee(s) au total\n"
		f"- {unpaid_count} facture(s) (vente + achat) impayee(s) ou en retard\n"
		f"- {backups_count} sauvegarde(s) de base de donnees disponible(s)\n"
		f"- Classement financier (pret_a_deployer/solide_mais_a_cadrer/risque_a_traiter/insuffisant) : {compteurs}\n"
	)


@frappe.whitelist()
def chat_with_assistant(message, history=None):
	frappe.only_for(_ASSISTANT_ALLOWED_ROLES)

	from sitiame_core.gemini_assistant import chat

	history = frappe.parse_json(history) if isinstance(history, str) else (history or [])

	messages = [{"role": "system", "content": _build_assistant_context()}]
	for turn in history[-10:]:
		if turn.get("role") in ("user", "assistant") and turn.get("content"):
			messages.append({"role": turn["role"], "content": turn["content"]})
	messages.append({"role": "user", "content": message})

	return chat(messages)


# PIN gate for the Club Sportif workspace (company accounts only -- see
# hide_club_sportif.js for the accompanying UI). This is a soft deterrent,
# not a real access boundary: Club Sportif's own links (Customer/
# Subscription/Event) stay reachable via direct URL for anyone who already
# has the underlying role-based permission, same as before. The PIN is
# only ever compared server-side (never shipped to the client) so it can't
# be read from page source, but that's the limit of what this buys.
@frappe.whitelist()
def verify_club_sportif_pin(pin):
	configured = frappe.conf.get("club_sportif_pin")
	if not configured:
		return {"ok": False}
	return {"ok": str(pin).strip() == str(configured).strip()}


# Inscription d'une nouvelle PME depuis le desk ERPNext (page "Inscrire une
# PME" du module Sitiame Core). PME360 reste la seule source de vérité pour
# les comptes PME (voir F-35) : cette fonction ne crée rien localement, elle
# relaie la demande à PME360 qui crée le compte, seede son plan comptable
# local et déclenche elle-même le provisionnement automatique de la société
# sur ERPNext (même chemin que /register ou l'espace Commercial de PME360).
@frappe.whitelist()
def register_pme_from_erpnext(name, email, company_name, phone=None, password=None,
	company_tax_id=None, rccm=None, city=None):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Réservé aux administrateurs."), frappe.PermissionError)

	base_url = (frappe.conf.get("pme360_base_url") or "https://sitiame-capital.com").rstrip("/")
	token = frappe.conf.get("pme360_webhook_token")
	if not token:
		frappe.throw(_("pme360_webhook_token n'est pas configuré dans site_config.json."))

	payload = {
		"name": name,
		"email": email,
		"company_name": company_name,
		"phone": phone,
		"password": password,
		"company_tax_id": company_tax_id,
		"rccm": rccm,
		"city": city,
	}

	try:
		response = requests.post(
			f"{base_url}/webhooks/erpnext/register-pme",
			json=payload,
			headers={"X-PME360-Webhook-Token": token},
			timeout=20,
		)
	except requests.RequestException as e:
		frappe.throw(_("PME360 injoignable : {0}").format(str(e)))

	if response.status_code >= 400:
		try:
			detail = response.json()
			message = detail.get("message") or detail.get("errors") or detail
		except ValueError:
			message = response.text
		frappe.throw(_("PME360 a refusé la demande : {0}").format(message))

	return response.json()


# Masquage de menu par utilisateur individuel (page "Gérer le menu"), en
# complément du masquage par rôle déjà natif à Frappe. Stocke la liste des
# link_to masqués pour un utilisateur donné dans son champ personnalisé
# sitiame_hidden_sidebar_items ; le filtrage réel se fait dans boot.py.
@frappe.whitelist()
def list_sidebar_items_for_menu_admin(sidebar_title="Organization"):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Réservé aux administrateurs."), frappe.PermissionError)

	doc = frappe.get_doc("Workspace Sidebar", sidebar_title)
	return [
		{"label": row.label, "link_to": row.link_to}
		for row in doc.items
		if row.type == "Link" and row.link_to
	]


@frappe.whitelist()
def get_user_hidden_sidebar_items(user):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Réservé aux administrateurs."), frappe.PermissionError)

	raw = frappe.db.get_value("User", user, "sitiame_hidden_sidebar_items")
	if not raw:
		return []
	try:
		return json.loads(raw)
	except ValueError:
		return []


@frappe.whitelist()
def set_user_hidden_sidebar_items(user, hidden_links):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Réservé aux administrateurs."), frappe.PermissionError)

	if isinstance(hidden_links, str):
		hidden_links = json.loads(hidden_links)

	frappe.db.set_value("User", user, "sitiame_hidden_sidebar_items", json.dumps(hidden_links))
	frappe.db.commit()
	return {"status": "ok", "hidden_count": len(hidden_links)}


@frappe.whitelist()
def list_desktop_icons_for_menu_admin():
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Réservé aux administrateurs."), frappe.PermissionError)

	rows = frappe.get_all(
		"Desktop Icon",
		filters=[["parent_icon", "in", ["", None]]],
		fields=["label"],
		order_by="idx asc",
	)
	# "Home" and "My Workspaces" are structural, always keep them visible.
	return [r for r in rows if r["label"] not in ("Home", "My Workspaces")]


@frappe.whitelist()
def get_user_hidden_desktop_icons(user):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Réservé aux administrateurs."), frappe.PermissionError)

	raw = frappe.db.get_value("User", user, "sitiame_hidden_desktop_icons")
	if not raw:
		return []
	try:
		return json.loads(raw)
	except ValueError:
		return []


@frappe.whitelist()
def set_user_hidden_desktop_icons(user, hidden_labels):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Réservé aux administrateurs."), frappe.PermissionError)

	if isinstance(hidden_labels, str):
		hidden_labels = json.loads(hidden_labels)

	frappe.db.set_value("User", user, "sitiame_hidden_desktop_icons", json.dumps(hidden_labels))
	frappe.db.commit()
	return {"status": "ok", "hidden_count": len(hidden_labels)}


@frappe.whitelist()
def save_user_menu_visibility(user, hidden_icons, hidden_items):
	"""Single call used by the "Gérer le menu" page: saves both lists, busts
	the server-side Desktop Icon cache (which is only rebuilt from bootinfo
	otherwise, so a stale cached list would keep showing on that user's next
	login even after this save), and pushes a realtime event so an already
	open browser tab for that user updates immediately instead of waiting
	for their next login.
	"""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Réservé aux administrateurs."), frappe.PermissionError)

	if isinstance(hidden_icons, str):
		hidden_icons = json.loads(hidden_icons)
	if isinstance(hidden_items, str):
		hidden_items = json.loads(hidden_items)

	frappe.db.set_value("User", user, "sitiame_hidden_desktop_icons", json.dumps(hidden_icons))
	frappe.db.set_value("User", user, "sitiame_hidden_sidebar_items", json.dumps(hidden_items))
	frappe.db.commit()

	from frappe.desk.doctype.desktop_icon.desktop_icon import clear_desktop_icons_cache

	clear_desktop_icons_cache(user)

	frappe.publish_realtime("sitiame_menu_updated", {}, user=user)

	return {"status": "ok"}


@frappe.whitelist()
def get_company_signup_info(company):
	"""Company identity captured at registration (Company Signup, filled on
	/company-signup or via the API registration flow), used to pre-fill the
	scoring dossier instead of re-typing it -- the dossier's own fields stay
	editable in case the signup record is missing or out of date.
	"""
	signup = frappe.db.get_value(
		"Company Signup",
		{"company": company},
		["contact_name", "phone", "rccm", "address", "city", "sector"],
		as_dict=True,
	)
	return signup or {}


def _score_to_note(score, thresholds=(85, 70, 55, 40, 20)):
	"""Converts a 0-100 continuous score into the dossier's 0-5 note scale."""
	if score is None:
		return None
	for i, threshold in enumerate(thresholds):
		if score >= threshold:
			return 5 - i
	return 0


def _ratio_to_note(ratio, thresholds=(2.5, 1.5, 1.0, 0.6, 0.0)):
	if ratio is None:
		return None
	for i, threshold in enumerate(thresholds):
		if ratio >= threshold:
			return 5 - i
	return 0


def _compute_payment_history(company):
	"""% of received Payment Entries that reached the linked Sales Invoice
	on or before its due_date -- the real "historique de paiement" signal."""
	rows = frappe.db.sql(
		"""
		select si.due_date as due_date, pe.posting_date as paid_date
		from `tabPayment Entry` pe
		inner join `tabPayment Entry Reference` per
			on per.parent = pe.name and per.reference_doctype = 'Sales Invoice'
		inner join `tabSales Invoice` si on si.name = per.reference_name
		where pe.company = %(company)s and pe.docstatus = 1 and pe.payment_type = 'Receive'
		""",
		{"company": company},
		as_dict=True,
	)

	if not rows:
		return None, "Aucun paiement client rapproché à une facture n'a été trouvé."

	on_time = sum(1 for r in rows if r.paid_date <= r.due_date)
	total = len(rows)
	pct_on_time = (on_time / total) * 100

	if pct_on_time >= 95:
		note = 5
	elif pct_on_time >= 85:
		note = 4
	elif pct_on_time >= 70:
		note = 3
	elif pct_on_time >= 50:
		note = 2
	elif pct_on_time > 0:
		note = 1
	else:
		note = 0

	explanation = f"{on_time}/{total} paiement(s) client reçu(s) à temps ({pct_on_time:.0f}%)."
	return note, explanation


def _compute_customer_concentration(company):
	"""Revenue concentration on the top customer + customer count -- proxy
	for "marché et clientèle": many customers with no single one dominating
	the revenue is a healthier market position than one or two large ones."""
	rows = frappe.db.sql(
		"""
		select customer, sum(grand_total) as total
		from `tabSales Invoice`
		where company = %(company)s and docstatus = 1
		group by customer
		order by total desc
		""",
		{"company": company},
		as_dict=True,
	)

	if not rows:
		return None, "Aucune facture de vente soumise n'a été trouvée pour cette société."

	total_revenue = sum(flt(r.total) for r in rows)
	if total_revenue <= 0:
		return None, "Le chiffre d'affaires facturé est nul."

	customer_count = len(rows)
	top_share = (flt(rows[0].total) / total_revenue) * 100

	if top_share <= 20 and customer_count >= 5:
		note = 5
	elif top_share <= 35 and customer_count >= 3:
		note = 4
	elif top_share <= 50:
		note = 3
	elif top_share <= 70:
		note = 2
	elif top_share <= 90:
		note = 1
	else:
		note = 0

	explanation = (
		f"{customer_count} client(s) facturé(s) ; le principal représente {top_share:.0f}% du chiffre d'affaires."
	)
	return note, explanation


@frappe.whitelist()
def get_scoring_suggestions(company):
	"""Suggested notes (0-5) for the Credit Scoring Dossier, computed from
	data already available in other ERPNext modules instead of asking the
	analyst to judge them blind:

	- Capacité de remboursement / Structure financière / Rentabilité /
	  Liquidité générale: all four now derive from Scoring 360's single
	  engine (sitiame_core.scoring360_service.score_company) -- capacité
	  de remboursement is the Bloc Banque total; structure financière and
	  rentabilité are that engine's own debt_asset/net_margin criterion
	  sub-scores, renormalised to 0-100 (score / configured weight * 100)
	  so they read on the same 0-100 scale _score_to_note expects;
	  liquidité générale is the engine's current_ratio.
	- Historique de paiement: % of Payment Entries that reached their
	  Sales Invoice on or before its due date.
	- Marché et clientèle: revenue concentration on the top customer.
	- Qualité des informations / Identité vérifiée: counts real KYC
	  documents attached to the Company (synced from PME360).

	Returns None for any criterion it can't support with real data (e.g.
	no accounting entries yet, or no sales invoices) -- the analyst still
	has full control, this only pre-fills a starting point with an
	explanation attached. Direction et organisation, Projet et
	financement, and Garanties et recouvrement stay manual: no reliable
	system signal exists for them.
	"""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Réservé aux administrateurs."), frappe.PermissionError)

	from sitiame_core.scoring360_service import _entries_count, get_config, score_company

	entries_count = _entries_count(company)

	kyc_count = frappe.db.count(
		"File", {"attached_to_doctype": "Company", "attached_to_name": company}
	)

	suggestions = {}

	if entries_count == 0:
		suggestions["capacite_remboursement"] = None
		suggestions["structure_financiere"] = None
		suggestions["rentabilite"] = None
		suggestions["liquidite_generale"] = None
		suggestions["_comptabilite_note"] = (
			"Aucune écriture comptable trouvée pour cette société : les critères financiers "
			"ne peuvent pas être suggérés automatiquement."
		)
	else:
		cfg = get_config()
		result = score_company(company)
		bank_block = result["blocks"]["bank"]
		internal_block = result["blocks"]["internal"]
		ratios = result["ratios"]

		bank_score = bank_block["total"]

		debt_asset_weight = float(cfg["bank"]["weights"].get("debt_asset") or 0)
		debt_asset_criterion = bank_block["criteria"].get("debt_asset") or {}
		structure_score = (
			(debt_asset_criterion["score"] / debt_asset_weight * 100)
			if debt_asset_weight and debt_asset_criterion.get("score") is not None
			else None
		)

		net_margin_weight = float(cfg["internal"]["weights"].get("net_margin") or 0)
		net_margin_criterion = internal_block["criteria"].get("net_margin") or {}
		rentabilite_score = (
			(net_margin_criterion["score"] / net_margin_weight * 100)
			if net_margin_weight and net_margin_criterion.get("score") is not None
			else None
		)

		liquidite_ratio = ratios.get("current_ratio")

		suggestions["capacite_remboursement"] = _score_to_note(bank_score)
		suggestions["structure_financiere"] = _score_to_note(structure_score)
		suggestions["rentabilite"] = _score_to_note(rentabilite_score)
		suggestions["liquidite_generale"] = _ratio_to_note(liquidite_ratio)
		suggestions["_comptabilite_note"] = (
			f"Calculé depuis {entries_count} écriture(s) comptable(s) : "
			f"score capacité remboursement (DSCR) {bank_score}/100, score structure financière {structure_score}, "
			f"score rentabilité {rentabilite_score}, ratio de liquidité générale {liquidite_ratio}."
		)

	payment_note, payment_explanation = _compute_payment_history(company)
	suggestions["historique_paiement"] = payment_note
	suggestions["_historique_paiement_note"] = payment_explanation

	market_note, market_explanation = _compute_customer_concentration(company)
	suggestions["marche_clientele"] = market_note
	suggestions["_marche_clientele_note"] = market_explanation

	suggestions["qualite_informations"] = 4 if kyc_count >= 2 else (2 if kyc_count == 1 else 0)
	suggestions["identity_verified"] = 1 if kyc_count >= 1 else 0
	suggestions["_kyc_note"] = (
		f"{kyc_count} document(s) KYC trouvé(s) pour cette société (synchronisés depuis PME360)."
	)

	return suggestions


@frappe.whitelist()
def get_financing_dossier_from_pme360(company):
	"""Pulls the latest FinancingDossier for this PME from PME360 (its
	analysts fill this in the /analyste wizard, not in ERPNext), same
	reverse-webhook pattern as register_pme_from_erpnext -- ERPNext calls
	PME360's read-only endpoint with the shared X-PME360-Webhook-Token.
	"""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Réservé aux administrateurs."), frappe.PermissionError)

	base_url = (frappe.conf.get("pme360_base_url") or "https://sitiame-capital.com").rstrip("/")
	token = frappe.conf.get("pme360_webhook_token")
	if not token:
		frappe.throw(_("pme360_webhook_token n'est pas configuré dans site_config.json."))

	try:
		response = requests.get(
			f"{base_url}/webhooks/erpnext/financing-dossier",
			params={"company": company},
			headers={"X-PME360-Webhook-Token": token},
			timeout=20,
		)
	except requests.RequestException as e:
		frappe.throw(_("PME360 injoignable : {0}").format(str(e)))

	if response.status_code >= 400:
		try:
			detail = response.json()
			message = detail.get("message") or detail
		except ValueError:
			message = response.text
		frappe.throw(_("PME360 a refusé la demande : {0}").format(message))

	return response.json()


PLATFORM_USERS_ALLOWED_EMAILS = {
	"fnguessan@sitiame-capital.com",
	"joseph@sitiame-capital.com",
	"kyliyanisse@gmail.com",
}


@frappe.whitelist()
def get_platform_users():
	"""Liste toutes les PME provisionnees avec leur statut d'abonnement et
	leur activite de connexion, pour la page admin "Utilisateurs de la
	plateforme". Reserve a une liste precise d'admins -- pas seulement
	System Manager, meme un autre admin ERPNext n'y a pas acces.
	"""
	if frappe.session.user not in PLATFORM_USERS_ALLOWED_EMAILS:
		frappe.throw(_("Reserve a certains administrateurs."), frappe.PermissionError)

	base_url = (frappe.conf.get("pme360_base_url") or "https://sitiame-capital.com").rstrip("/")
	token = frappe.conf.get("pme360_webhook_token")
	if not token:
		frappe.throw(_("pme360_webhook_token n'est pas configure dans site_config.json."))

	try:
		response = requests.get(
			f"{base_url}/webhooks/erpnext/platform-users",
			headers={"X-PME360-Webhook-Token": token},
			timeout=20,
		)
	except requests.RequestException as e:
		frappe.throw(_("PME360 injoignable : {0}").format(str(e)))

	if response.status_code >= 400:
		try:
			detail = response.json()
			message = detail.get("message") or detail
		except ValueError:
			message = response.text
		frappe.throw(_("PME360 a refuse la demande : {0}").format(message))

	return response.json()
