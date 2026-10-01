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
WEB_ASSETS_VERSION = "2026100101"

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
	"/assets/sitiame_core/js/green_desktop_icons_enforce.js",
	"/assets/sitiame_core/js/subscription_banner.js",
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

doctype_js = {"User": "public/js/user_charge_affaires.js"}

# A chargé d'affaires only sees his portfolio of PMEs (portfolio.py)
from sitiame_core.portfolio import PORTFOLIO_DOCTYPES as _PORTFOLIO_DOCTYPES

permission_query_conditions.update(
	{doctype: "sitiame_core.portfolio.get_permission_query_conditions" for doctype in _PORTFOLIO_DOCTYPES}
)
has_permission.update({doctype: "sitiame_core.portfolio.has_permission" for doctype in _PORTFOLIO_DOCTYPES})

doc_events = {
	# An invoice marked paid gets its Payment Entry at validation (pay_on_submit.py)
	"Purchase Invoice": {"on_submit": "sitiame_core.pay_on_submit.create_payment"},
	"Sales Invoice": {"on_submit": "sitiame_core.pay_on_submit.create_payment"},
	# a chargé d'affaires proposes, a validator decides (portfolio.py)
	"Credit Scoring Dossier": {"validate": "sitiame_core.portfolio.check_decision"},
	"Financing Dossier": {"validate": "sitiame_core.portfolio.check_decision"},
	"Company": {"validate": "sitiame_core.portfolio.guard_portfolio_field"},
	# a PME registered by a chargé d'affaires joins his portfolio once its
	# company is provisioned (portfolio.py)
	"User Permission": {"after_insert": "sitiame_core.portfolio.assign_pending_pme"},
}

extend_bootinfo ="sitiame_core.boot.extend_bootinfo"

after_migrate = "sitiame_core.setup.after_migrate"

scheduler_events = {
	"daily": [
		"sitiame_core.tasks.block_expired_trials",
	],
	"cron": {
		"0 */4 * * *": ["sitiame_core.tasks.run_scheduled_backup"],
		# 02:30, off the 4-hourly database backups
		"30 2 * * *": ["sitiame_core.tasks.run_daily_files_backup"],
		# settles Jèko payments whose webhook was lost (subscription_api)
		"*/10 * * * *": ["sitiame_core.subscription_api.reconcile_pending_payments"],
	},
}
