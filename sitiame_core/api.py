# Copyright (c) 2026, Sitiame Capital
# License: MIT

import os
import re
import shutil
import sys
import time
from datetime import datetime

import requests

import frappe
from frappe import _
from frappe.utils import get_backups_path, get_bench_path

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
