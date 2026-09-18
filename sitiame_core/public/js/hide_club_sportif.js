// Purely cosmetic: removes the "Club Sportif" workspace shortcut from the
// home icon grid and the app switcher for company accounts (no System
// Manager / Workspace Manager role). This is NOT a security boundary --
// Club Sportif's own links (Membres/Cotisations/Evenements) point at
// plain Customer/Subscription/Event, which company accounts can already
// read via their normal Sales/Accounts Manager roles for real business
// use. block_modules was tried first and proven to have zero effect on
// workspace visibility in this Frappe version (a workspace shows as soon
// as the user can read any doctype it links to), so this just declutters
// the UI instead of pretending to restrict data that was always
// accessible anyway.
(function () {
	function isAdmin() {
		var roles = (frappe.boot && frappe.boot.user && frappe.boot.user.roles) || [];
		return roles.indexOf("System Manager") !== -1 || roles.indexOf("Workspace Manager") !== -1;
	}

	function hideClubSportif() {
		if (isAdmin()) return;

		document.querySelectorAll(".widget, .app-icon, a, div").forEach(function (el) {
			if (el.children.length > 3) return;
			var text = (el.textContent || "").trim();
			if (text === "Club Sportif") {
				var card = el.closest(".widget, .app-icon") || el;
				card.style.display = "none";
			}
		});
	}

	document.addEventListener("DOMContentLoaded", function () {
		setTimeout(hideClubSportif, 500);
		setTimeout(hideClubSportif, 1500);
	});
	$(document).on("app_ready", function () {
		setTimeout(hideClubSportif, 300);
	});
	$(document).on("page-change", function () {
		setTimeout(hideClubSportif, 300);
	});
})();
