// Adds a small FR/EN button to the desk navbar. Clicking it saves the
// choice on the current User's "language" field (persists across
// reload/logout, since it's stored on the account, not just the browser)
// and reloads the page so the new language takes effect immediately.
(function () {
	function currentLang() {
		return (window.frappe && frappe.boot && frappe.boot.lang) || "en";
	}

	function setLanguage(lang) {
		if (!window.frappe || !frappe.csrf_token) return;

		fetch("/api/method/frappe.client.set_value", {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				"X-Frappe-CSRF-Token": frappe.csrf_token,
			},
			body: JSON.stringify({
				doctype: "User",
				name: frappe.session.user,
				fieldname: "language",
				value: lang,
			}),
		}).then(function () {
			window.location.reload();
		});
	}

	function addButton() {
		if (document.getElementById("sitiame-lang-switch")) return;
		var navbar = document.querySelector(".navbar-right, .navbar-collapse, header");
		if (!navbar) return;

		var wrap = document.createElement("div");
		wrap.id = "sitiame-lang-switch";
		wrap.style.display = "flex";
		wrap.style.alignItems = "center";
		wrap.style.gap = "4px";
		wrap.style.marginRight = "10px";
		wrap.style.order = "-1";

		["fr", "en"].forEach(function (lang) {
			var btn = document.createElement("button");
			btn.type = "button";
			btn.textContent = lang.toUpperCase();
			btn.title = lang === "fr" ? "Passer en français" : "Switch to English";
			var active = currentLang() === lang;
			btn.style.cssText =
				"font-size:11px;font-weight:600;padding:2px 7px;border-radius:4px;cursor:pointer;" +
				"border:1px solid #05157c;background:" +
				(active ? "#05157c" : "#fff") +
				";color:" +
				(active ? "#fff" : "#05157c") +
				";";
			btn.addEventListener("click", function () {
				setLanguage(lang);
			});
			wrap.appendChild(btn);
		});

		navbar.insertBefore(wrap, navbar.firstChild);
	}

	if (window.frappe && frappe.ready) {
		frappe.ready(function () {
			setTimeout(addButton, 800);
		});
	}
	document.addEventListener("DOMContentLoaded", function () {
		setTimeout(addButton, 1200);
	});
})();
