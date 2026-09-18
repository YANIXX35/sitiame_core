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
]

scheduler_events = {
	"daily": [
		"sitiame_core.tasks.block_expired_trials",
	],
	"cron": {
		"0 */4 * * *": ["sitiame_core.tasks.run_scheduled_backup"],
	},
}
