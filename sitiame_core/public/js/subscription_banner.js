// Renewal banner for PME accounts, driven by frappe.boot.sitiame_subscription
// (see boot.py). Never blocks anything: it only points to the Abonnement
// page. Hidden on that page itself so it doesn't sit on top of the checkout.
(function () {
	var BANNER_ID = "sitiame-subscription-banner";
	var WARN_DAYS = 5;
	// Session key: the banner can be dismissed for the current session.
	// It reappears on next login so the user is never permanently blind to it.
	var DISMISSED_KEY = "sitiame_sub_banner_dismissed";

	function formatDate(value) {
		return frappe.datetime.str_to_user(value);
	}

	function daysLeft(value) {
		return frappe.datetime.get_day_diff(value, frappe.datetime.get_today());
	}

	function isDismissed() {
		try { return sessionStorage.getItem(DISMISSED_KEY) === "1"; } catch (e) { return false; }
	}

	function dismiss() {
		try { sessionStorage.setItem(DISMISSED_KEY, "1"); } catch (e) {}
		var el = document.getElementById(BANNER_ID);
		if (el) el.remove();
	}

	function getMessage(sub) {
		if (sub.active) {
			var left = daysLeft(sub.ends_on);
			if (left > WARN_DAYS) return null;
			return {
				color: "#b45309",
				background: "#fffbeb",
				text: __("Abonnement SITIAME : expire le {0}.", [formatDate(sub.ends_on)]),
			};
		}
		if (sub.in_trial) {
			return {
				color: "#b45309",
				background: "#fffbeb",
				text: __("Essai gratuit jusqu'au {0}.", [formatDate(sub.trial_ends_on)]),
			};
		}
		return {
			color: "#b91c1c",
			background: "#fef2f2",
			text: sub.ends_on
				? __("Abonnement SITIAME expiré le {0}.", [formatDate(sub.ends_on)])
				: __("Période d'essai terminée — aucun abonnement actif."),
		};
	}

	function render() {
		var sub = frappe.boot && frappe.boot.sitiame_subscription;
		var existing = document.getElementById(BANNER_ID);
		var onSubscriptionPage = (frappe.get_route() || [])[0] === "erp-abonnement";
		var message = sub && !onSubscriptionPage && !isDismissed() ? getMessage(sub) : null;

		if (!message) {
			if (existing) existing.remove();
			return;
		}
		if (existing) return;

		var banner = document.createElement("div");
		banner.id = BANNER_ID;
		banner.style.cssText =
			"display:flex;align-items:center;gap:8px;" +
			"padding:6px 12px;font-size:13px;font-weight:500;border-bottom:1px solid;" +
			"color:" + message.color + ";background:" + message.background + ";border-color:" + message.color + "33;";

		var text = document.createElement("span");
		text.style.cssText = "flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;";
		text.textContent = message.text;
		text.title = message.text; // tooltip pour voir le texte complet si tronqué

		var link = document.createElement("a");
		link.href = "/app/erp-abonnement";
		link.textContent = __("S'abonner");
		link.style.cssText =
			"flex:none;font-weight:700;text-decoration:underline;color:" + message.color +
			";white-space:nowrap;";

		var close = document.createElement("button");
		close.type = "button";
		close.setAttribute("aria-label", __("Fermer"));
		close.innerHTML = "&times;";
		close.style.cssText =
			"flex:none;border:none;background:none;color:" + message.color +
			";font-size:18px;line-height:1;padding:0 2px;cursor:pointer;opacity:.7;";
		close.addEventListener("click", dismiss);

		banner.appendChild(text);
		banner.appendChild(link);
		banner.appendChild(close);

		var navbar = document.querySelector("header.navbar") || document.querySelector(".navbar");
		if (navbar && navbar.parentNode) {
			navbar.parentNode.insertBefore(banner, navbar.nextSibling);
		} else {
			document.body.insertBefore(banner, document.body.firstChild);
		}
	}

	$(document).on("app_ready", function () {
		render();
		frappe.router.on("change", render);
	});
})();
