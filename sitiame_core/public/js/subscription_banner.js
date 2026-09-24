// Renewal banner for PME accounts, driven by frappe.boot.sitiame_subscription
// (see boot.py). Never blocks anything: it only points to the Abonnement
// page. Hidden on that page itself so it doesn't sit on top of the checkout.
(function () {
	var BANNER_ID = "sitiame-subscription-banner";
	var WARN_DAYS = 5;

	function formatDate(value) {
		return frappe.datetime.str_to_user(value);
	}

	function daysLeft(value) {
		return frappe.datetime.get_day_diff(value, frappe.datetime.get_today());
	}

	function getMessage(sub) {
		if (sub.active) {
			var left = daysLeft(sub.ends_on);
			if (left > WARN_DAYS) return null;
			return {
				color: "#b45309",
				background: "#fffbeb",
				text: __("Votre abonnement SITIAME se termine le {0}.", [formatDate(sub.ends_on)]),
			};
		}
		if (sub.in_trial) {
			return {
				color: "#b45309",
				background: "#fffbeb",
				text: __("Période d'essai gratuite jusqu'au {0}.", [formatDate(sub.trial_ends_on)]),
			};
		}
		return {
			color: "#b91c1c",
			background: "#fef2f2",
			text: sub.ends_on
				? __("Votre abonnement SITIAME a expiré le {0}.", [formatDate(sub.ends_on)])
				: __("Votre période d'essai est terminée et aucun abonnement SITIAME n'est actif."),
		};
	}

	function render() {
		var sub = frappe.boot && frappe.boot.sitiame_subscription;
		var existing = document.getElementById(BANNER_ID);
		var onSubscriptionPage = (frappe.get_route() || [])[0] === "erp-abonnement";
		var message = sub && !onSubscriptionPage ? getMessage(sub) : null;

		if (!message) {
			if (existing) existing.remove();
			return;
		}
		if (existing) return;

		var banner = document.createElement("div");
		banner.id = BANNER_ID;
		banner.style.cssText =
			"display:flex;align-items:center;justify-content:center;gap:12px;flex-wrap:wrap;" +
			"padding:8px 16px;font-size:13px;font-weight:500;border-bottom:1px solid;" +
			"color:" + message.color + ";background:" + message.background + ";border-color:" + message.color + "33;";

		var text = document.createElement("span");
		text.textContent = message.text;

		var link = document.createElement("a");
		link.href = "/app/erp-abonnement";
		link.textContent = __("Renouveler / S'abonner (15 000 FCFA / mois)");
		link.style.cssText = "font-weight:700;text-decoration:underline;color:" + message.color + ";";

		banner.appendChild(text);
		banner.appendChild(link);

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
