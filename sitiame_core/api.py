# Copyright (c) 2026, Sitiame Capital
# License: MIT

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
			"terms_accepted": 1,
			"terms_accepted_at": frappe.utils.now_datetime(),
			"signup_ip": frappe.local.request_ip,
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
	"""ERPNext port of PME360's classementPlateforme(): ranks every ERPNext
	Company as financable/solvable_seulement/non_retenu/insuffisant from
	its own GL Entry data. See financial_ratio_service.py."""
	frappe.only_for("System Manager")

	from sitiame_core.financial_ratio_service import classement_erpnext

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
		from sitiame_core.financial_ratio_service import classement_erpnext

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
		f"- Classement financier : {compteurs}\n"
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
