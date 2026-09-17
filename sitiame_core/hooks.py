app_name = "sitiame_core"
app_title = "Sitiame Core"
app_publisher = "Sitiame Capital"
app_description = "Inscription entreprise publique sur ERPNext, avec creation automatique de Company + User, connexion automatique et redirection vers /app."
app_email = "contact@sitiame-capital.com"
app_license = "MIT"

required_apps = ["erpnext"]

web_include_js = "/assets/sitiame_core/js/login_signup_link.js"
app_include_js = "/assets/sitiame_core/js/language_switcher.js"

scheduler_events = {
	"daily": [
		"sitiame_core.tasks.block_expired_trials",
	]
}
