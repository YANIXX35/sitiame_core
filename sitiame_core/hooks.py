app_name = "sitiame_core"
app_title = "Sitiame Core"
app_publisher = "Sitiame Capital"
app_description = "Inscription entreprise publique sur ERPNext, avec creation automatique de Company + User, connexion automatique et redirection vers /app."
app_email = "contact@sitiame-capital.com"
app_license = "MIT"

required_apps = ["erpnext"]

web_include_js = [
	"/assets/sitiame_core/js/login_signup_link.js",
	"/assets/sitiame_core/js/sitiame_login.js",
]
web_include_css = "/assets/sitiame_core/css/sitiame_login.css"
app_include_js = [
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
]

doctype_list_js = {
	"Purchase Invoice": "public/js/ocr_invoice_list.js",
	"Sales Invoice": "public/js/ocr_invoice_list.js",
}

extend_bootinfo = "sitiame_core.boot.extend_bootinfo"

after_migrate = "sitiame_core.setup.after_migrate"

scheduler_events = {
	"daily": [
		"sitiame_core.tasks.block_expired_trials",
	],
	"cron": {
		"0 */4 * * *": ["sitiame_core.tasks.run_scheduled_backup"],
	},
}
