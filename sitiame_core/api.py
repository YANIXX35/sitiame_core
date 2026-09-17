# Copyright (c) 2026, Sitiame Capital
# License: MIT

import re

import requests

import frappe
from frappe import _

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
			# Deliberately NOT "System Manager": that role bypasses block_modules
			# (Frappe treats it as admin-equivalent for the trial-blocking check
			# in desk.py), which would make the 1-month trial cutoff a no-op.
			# Deliberately no "Projects Manager": the company dashboard should not
			# expose Projets (or Organisation/Club Sportif, which carry no
			# ERPNext business role at all and are Sitiame-internal/admin-only).
			"roles": [
				{"role": "Accounts Manager"},
				{"role": "Sales Manager"},
				{"role": "Purchase Manager"},
				{"role": "Stock Manager"},
				{"role": "Manufacturing Manager"},
				{"role": "Quality Manager"},
			],
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


# Basic invoice-scan extraction (v1): pulls raw text via OCR.space plus a
# best-effort total amount and date, for the user to complete manually.
# Deliberately not a port of PME360's full field-by-field extraction
# pipeline (app/Services/OcrService.php) -- that's a much larger, separate
# piece of work if/when needed.
_AMOUNT_PATTERN = re.compile(
	r"(?:TOTAL|MONTANT|NET\s*A\s*PAYER)[^\d]{0,20}([\d][\d\s.,]{2,})", re.IGNORECASE
)
_DATE_PATTERN = re.compile(r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\b")
_CLIENT_PATTERN = re.compile(r"(?:Client|Fournisseur)\s*[:\-]\s*(.+)", re.IGNORECASE)


def _parse_amount(raw: str) -> float | None:
	digits = re.sub(r"[^\d,\.]", "", raw)
	digits = digits.replace(" ", "")
	# normalise "1.234.567,89" or "1 234 567" style groupings to a float
	if "," in digits and "." in digits:
		digits = digits.replace(".", "").replace(",", ".")
	elif "," in digits:
		digits = digits.replace(",", ".")
	try:
		return float(digits)
	except ValueError:
		return None


def _best_guess_amount(text: str) -> float | None:
	matches = _AMOUNT_PATTERN.findall(text)
	amounts = [a for a in (_parse_amount(m) for m in matches) if a]
	return max(amounts) if amounts else None


def _best_guess_date(text: str) -> str | None:
	match = _DATE_PATTERN.search(text)
	if not match:
		return None
	raw = match.group(1)
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


def _best_guess_client(text: str) -> str | None:
	match = _CLIENT_PATTERN.search(text)
	if not match:
		return None
	name = match.group(1).strip()
	return name or None


@frappe.whitelist()
def ocr_extract_invoice(file_url):
	"""Send an already-uploaded file (PDF/image) to OCR.space and return
	the raw text plus a best-effort amount/date guess.

	Uploaded files are private by default, so OCR.space can't fetch them
	back over the "url" param (it isn't authenticated against this site) --
	the file bytes are read locally and posted directly instead.
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

	return {
		"text": text,
		"amount": _best_guess_amount(text),
		"date": _best_guess_date(text),
		"client_name": _best_guess_client(text),
	}
