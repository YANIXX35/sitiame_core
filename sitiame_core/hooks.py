app_name = "sitiame_core"
app_title = "Sitiame Core"
app_publisher = "Sitiame Capital"
app_description = "Inscription entreprise publique sur ERPNext, avec creation automatique de Company + User, connexion automatique et redirection vers /app."
app_email = "contact@sitiame-capital.com"
app_license = "MIT"

required_apps = ["erpnext"]

# These files are served without a hash in their name: browsers kept an
# old copy after a deploy (2026-10-01, login signup link). Bump WEB_ASSETS_VERSION
# whenever one of them changes.
WEB_ASSETS_VERSION = "2026100701"

web_include_js = [
	f"/assets/sitiame_core/js/pwa.js?v={WEB_ASSETS_VERSION}",
	f"/assets/sitiame_core/js/login_signup_link.js?v={WEB_ASSETS_VERSION}",
	f"/assets/sitiame_core/js/sitiame_login.js?v={WEB_ASSETS_VERSION}",
]
web_include_css = f"/assets/sitiame_core/css/sitiame_login.css?v={WEB_ASSETS_VERSION}"

# Installable app: serves /manifest.webmanifest and /sitiame-sw.js
page_renderer = ["sitiame_core.pwa.PWARenderer"]

app_include_js = [
	"/assets/sitiame_core/js/pwa.js",
	"/assets/sitiame_core/js/language_switcher.js",
	"/assets/sitiame_core/js/sales_invoice_ocr_import.js",
	"/assets/sitiame_core/js/scoring360_settings_test.js",
	"/assets/sitiame_core/js/ai_assistant.js",
	"/assets/sitiame_core/js/menu_visibility_watcher.js",
	"/assets/sitiame_core/js/syscohada_statements.js",
	"/assets/sitiame_core/js/green_desktop_icons_enforce.js",
	"/assets/sitiame_core/js/subscription_banner.js",
	"/assets/sitiame_core/js/onboarding.js",
	"/assets/sitiame_core/js/account_warehouse.js",
]
app_include_css = [
	"/assets/sitiame_core/css/green_desktop_icons.css",
	"/assets/sitiame_core/css/sitiame_mobile.css",
]

doctype_list_js = {
	"Purchase Invoice": ["public/js/ocr_invoice_list.js", "public/js/list_download.js"],
	"Sales Invoice": ["public/js/ocr_invoice_list.js", "public/js/list_download.js"],
	"Payment Entry": ["public/js/ocr_invoice_list.js", "public/js/list_download.js"],
	"Journal Entry": "public/js/list_download.js",
	"Stock Entry": "public/js/list_download.js",
	"Purchase Receipt": "public/js/list_download.js",
	"Delivery Note": "public/js/list_download.js",
	"Purchase Order": "public/js/list_download.js",
	"Sales Order": "public/js/list_download.js",
	"Item": "public/js/list_download.js",
}

# Staff accounts don't see each other's business documents (staff_isolation.py)
from sitiame_core.staff_isolation import ISOLATED_DOCTYPES as _ISOLATED_DOCTYPES

permission_query_conditions = {
	doctype: "sitiame_core.staff_isolation.get_permission_query_conditions"
	for doctype in _ISOLATED_DOCTYPES
}
has_permission = {
	doctype: "sitiame_core.staff_isolation.has_permission" for doctype in _ISOLATED_DOCTYPES
}

# a supplier name already used by another PME gets " - N" (overrides.py)
override_doctype_class = {"Supplier": "sitiame_core.overrides.SitiameSupplier"}

doctype_js = {
	"User": "public/js/user_charge_affaires.js",
	# "Modifier le devis": cancel + amend in one step (quotation.py)
	"Quotation": "public/js/quotation.js",
}

# A chargé d'affaires only sees his portfolio of PMEs (portfolio.py)
from sitiame_core.portfolio import PORTFOLIO_DOCTYPES as _PORTFOLIO_DOCTYPES

permission_query_conditions.update(
	{doctype: "sitiame_core.portfolio.get_permission_query_conditions" for doctype in _PORTFOLIO_DOCTYPES}
)
has_permission.update({doctype: "sitiame_core.portfolio.has_permission" for doctype in _PORTFOLIO_DOCTYPES})

# PME Client access restricted by offer level (offer_access.py)
from sitiame_core.offer_access import OFFER_RESTRICTED_DOCTYPES as _OFFER_RESTRICTED_DOCTYPES

permission_query_conditions.update(
    {doctype: "sitiame_core.offer_access.get_permission_query_conditions" for doctype in _OFFER_RESTRICTED_DOCTYPES}
)
has_permission.update({doctype: "sitiame_core.offer_access.has_permission" for doctype in _OFFER_RESTRICTED_DOCTYPES})

# A PME account's ledger is the one of its own vouchers (liasse_scope.py)
from sitiame_core.liasse_scope import LEDGER_DOCTYPES as _LEDGER_DOCTYPES

permission_query_conditions.update(
	{doctype: "sitiame_core.liasse_scope.get_permission_query_conditions" for doctype in _LEDGER_DOCTYPES}
)
has_permission.update({doctype: "sitiame_core.liasse_scope.has_permission" for doctype in _LEDGER_DOCTYPES})
# ... and its stock the one of its own warehouse (account_warehouse.py)
before_request = [
	"sitiame_core.liasse_scope.patch_unscoped_reports",
	"sitiame_core.account_warehouse.patch_stock_reports",
	"sitiame_core.setup_guard.block_setup_wizard_for_pme",
]
before_job = before_request

# Shared lists (groups, territories, price lists, units...): read-only for
# a PME, maintained by Sitiame staff (shared_masters.py)
from sitiame_core.shared_masters import SHARED_MASTERS as _SHARED_MASTERS

has_permission.update({doctype: "sitiame_core.shared_masters.has_permission" for doctype in _SHARED_MASTERS})

doc_events = {
	# Scan antivirus ClamAV sur chaque fichier uploadé (clamav_scanner.py)
	"File": {
		"after_insert": "sitiame_core.clamav_scanner.scan_uploaded_file",
	},
	# Email entrant avec pièce jointe → Incoming Document (pipeline.py)
	"Communication": {
		"after_insert": "sitiame_core.incoming_document_pipeline.create_from_email"
	},
	# An invoice marked paid gets its Payment Entry at validation (pay_on_submit.py)
	"Purchase Invoice": {
		# Corrige l'imputation 4081→6011 quand update_stock=0 (account_guard.py)
		"before_submit": "sitiame_core.account_guard.validate_purchase_expense_account",
		"on_submit": "sitiame_core.pay_on_submit.create_payment",
	},
	"Sales Invoice": {
		# Assign FNE number (Facture Normalisée Électronique — DGI CI obligation)
		"before_submit": "sitiame_core.fne.assign_fne_number",
		"on_submit": "sitiame_core.pay_on_submit.create_payment",
	},
	"Payment Entry": {
		"on_submit": "sitiame_core.auto_reconcile.on_payment_submit",
	},
	# a chargé d'affaires proposes, a validator decides (portfolio.py)
	"Credit Scoring Dossier": {"validate": "sitiame_core.portfolio.check_decision"},
	"Financing Dossier": {"validate": "sitiame_core.portfolio.check_decision"},
	"Company": {
		# every new company on the SYSCOHADA chart with codes (company_chart.py)
		"before_insert": "sitiame_core.company_chart.force_syscohada_chart",
		"validate": "sitiame_core.portfolio.guard_portfolio_field",
		"after_insert": "sitiame_core.scripts.mise_en_oeuvre_exercices.provisionner_societe",
		"on_update": [
			"sitiame_core.company_chart.set_syscohada_defaults",
			# document numbers of its own (naming.py)
			"sitiame_core.naming.on_company_update",
			# sync the PME's offer role when sitiame_offer changes on the Company
			"sitiame_core.offer_roles.sync_offer_role_on_company_update",
		],
	},
	# every company numbers the new year's documents on its own (naming.py)
	"Fiscal Year": {"on_update": "sitiame_core.naming.on_fiscal_year_update"},
	# Gel automatique des comptes à la création d'une société (mise_en_oeuvre_exercices.py)
	# Note : Company already has before_insert/validate/on_update above; after_insert is new.
	# Dérogation de période : accordée et révoquée via Ouverture Exceptionnelle de Periode
	"Ouverture Exceptionnelle de Periode": {
		"on_submit": "sitiame_core.scripts.mise_en_oeuvre_exercices.ouvrir_derogation",
		"on_cancel": "sitiame_core.scripts.mise_en_oeuvre_exercices.fermer_derogation",
	},
	# a PME registered by a chargé d'affaires joins his portfolio once its
	# company is provisioned (portfolio.py); the PME user's own Contact
	# joins its company (party_isolation.py)
	"User Permission": {
		"after_insert": [
			"sitiame_core.portfolio.assign_pending_pme",
			"sitiame_core.party_isolation.attach_user_contacts",
			# each PME account has its own warehouse (account_warehouse.py)
			"sitiame_core.account_warehouse.on_company_permission",
		]
	},
}

# A PME only sees its own customers, suppliers, contacts, addresses: each
# gets a company on creation (party_isolation.py)
from sitiame_core.party_isolation import PARTY_DOCTYPES as _PARTY_DOCTYPES

for _doctype in _PARTY_DOCTYPES:
	doc_events.setdefault(_doctype, {})["before_insert"] = "sitiame_core.party_isolation.set_company"
	doc_events[_doctype]["before_save"] = "sitiame_core.party_isolation.protect_company"

# a PME account's stock documents use its own warehouse (account_warehouse.py)
from sitiame_core.account_warehouse import STOCK_DOCTYPES as _STOCK_DOCTYPES

for _doctype in _STOCK_DOCTYPES:
	_events = doc_events.setdefault(_doctype, {})
	_existing = _events.get("before_validate")
	_events["before_validate"] = [
		*([] if not _existing else _existing if isinstance(_existing, list) else [_existing]),
		"sitiame_core.account_warehouse.set_account_warehouse",
	]

extend_bootinfo = "sitiame_core.boot.extend_bootinfo"

# a desk account tied to no company logs in only if it is Sitiame staff (access_guard.py)
on_session_creation = "sitiame_core.access_guard.check_login"

update_website_context = ["sitiame_core.website_branding.get_context"]

after_migrate = "sitiame_core.setup.after_migrate"

scheduler_events = {
	"daily": [
		"sitiame_core.tasks.block_expired_trials",
		# lettre automatiquement paiements ↔ factures chaque nuit (auto_reconcile.py)
		"sitiame_core.auto_reconcile.run_daily",
	],
	"hourly": [
		# referme automatiquement les dérogations de période expirées (mise_en_oeuvre_exercices.py)
		"sitiame_core.scripts.mise_en_oeuvre_exercices.fermer_derogations_echues",
	],
	"cron": {
		"0 */4 * * *": ["sitiame_core.tasks.run_scheduled_backup"],
		# 02:30, off the 4-hourly database backups
		"30 2 * * *": ["sitiame_core.tasks.run_daily_files_backup"],
		# settles Jèko payments whose webhook was lost (subscription_api)
		"*/10 * * * *": ["sitiame_core.subscription_api.reconcile_pending_payments"],
		# clôture mensuelle automatique le 10 à 02:00 (mise_en_oeuvre_exercices.py)
		"0 2 10 * *": ["sitiame_core.scripts.mise_en_oeuvre_exercices.cloture_mensuelle_auto"],
		# clôture mensuelle automatique le 1er de chaque mois à 06:00 (monthly_close.py)
		"0 6 1 * *": ["sitiame_core.monthly_close.run_monthly_task"],
	},
}
