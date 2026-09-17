// block_modules (Frappe's built-in User field) restricts sidebar navigation
// and deeper permission checks, but does NOT hide the home-page icon grid
// by itself. This fetches which workspaces are blocked for the current
// user and removes their icons from the desk home page.
(function () {
	function slugify(name) {
		return name.toLowerCase().replace(/\s+/g, "-");
	}

	function hideBlockedIcons() {
		if (!window.frappe || !frappe.csrf_token) return;

		fetch("/api/method/sitiame_core.tasks.get_my_blocked_workspaces", {
			headers: { "X-Frappe-CSRF-Token": frappe.csrf_token },
		})
			.then(function (res) {
				return res.json();
			})
			.then(function (data) {
				var blockedNames = data.message || [];
				if (!blockedNames.length) return;

				var blockedSlugs = blockedNames.map(slugify);

				document.querySelectorAll("a[href]").forEach(function (a) {
					var href = (a.getAttribute("href") || "").toLowerCase();
					var isBlocked = blockedSlugs.some(function (slug) {
						return href.indexOf("/" + slug) !== -1;
					});
					if (!isBlocked) return;

					var tile =
						a.closest(".widget, .standard-sidebar-item, .app-icon-wrapper, .module-item") || a;
					tile.style.display = "none";
				});
			})
			.catch(function () {
				// silent: worst case the icon stays visible, no functional impact
			});
	}

	if (window.frappe && frappe.ready) {
		frappe.ready(function () {
			setTimeout(hideBlockedIcons, 800);
		});
	}
	document.addEventListener("DOMContentLoaded", function () {
		setTimeout(hideBlockedIcons, 1200);
	});

	// desk is a single-page app: re-check after route changes back to Home
	if (window.frappe && frappe.router && frappe.router.on) {
		frappe.router.on("change", function () {
			setTimeout(hideBlockedIcons, 500);
		});
	}
})();
