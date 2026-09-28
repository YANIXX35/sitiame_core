// Adds a small FR/EN button to the desk. Clicking it saves the choice on
// the current User's "language" field (persists across reload/logout,
// since it's stored on the account, not just the browser) and reloads the
// page so the new language takes effect immediately.
//
// Placement: the desk home's top bar, and on every other page the bottom
// of the sidebar, just above the user block. It used to go into the first
// <header> found, which on a list page is the list's column header -- the
// switch ended up among the column titles.
(function () {
	var SWITCH_ID = "sitiame-lang-switch";

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

	function buildSwitch() {
		var wrap = document.createElement("div");
		wrap.id = SWITCH_ID;
		wrap.style.display = "flex";
		wrap.style.alignItems = "center";
		wrap.style.gap = "4px";

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
		return wrap;
	}

	function visible(el) {
		return !!(el && el.offsetParent);
	}

	function place() {
		if (!window.frappe || !frappe.session || frappe.session.user === "Guest") return;
		var wrap = document.getElementById(SWITCH_ID) || buildSwitch();

		var homeBar = document.querySelector(".desktop-wrapper .desktop-navbar");
		if (visible(homeBar)) {
			if (wrap.parentElement !== homeBar) homeBar.insertBefore(wrap, homeBar.firstChild);
			wrap.style.margin = "0 10px 0 0";
			return;
		}

		var userBlock = document.querySelector(".body-sidebar .body-sidebar-bottom");
		if (userBlock && userBlock.parentElement) {
			if (wrap.nextElementSibling !== userBlock) userBlock.parentElement.insertBefore(wrap, userBlock);
			wrap.style.margin = "0 0 8px 12px";
		}
	}

	function placeSoon() {
		setTimeout(place, 300);
	}

	if (window.jQuery) {
		window.jQuery(document).on("app_ready", function () {
			placeSoon();
			if (frappe.router && frappe.router.on) frappe.router.on("change", placeSoon);
		});
	}
	document.addEventListener("DOMContentLoaded", function () {
		setTimeout(place, 1200);
	});
})();
