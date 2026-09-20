// PIN gate for the Club Sportif workspace, replacing the pure visual hide
// as a test (see api.py::verify_club_sportif_pin). NOT a real access
// boundary -- Club Sportif's own links (Membres/Cotisations/Evenements)
// point at plain Customer/Subscription/Event, which company accounts can
// already read via their normal Sales/Accounts Manager roles for real
// business use. This only stops casual/accidental navigation to the
// workspace route itself; the PIN is checked server-side so it can't be
// read from page source, but a technical user could still reach the
// underlying doctypes directly (e.g. /app/customer).
(function () {
	var LOCK_ROUTE_FRAGMENT = "club-sportif";
	var SESSION_KEY = "sitiame-pin-unlocked-club-sportif";

	function isAdmin() {
		var roles = (frappe.boot && frappe.boot.user && frappe.boot.user.roles) || [];
		return roles.indexOf("System Manager") !== -1 || roles.indexOf("Workspace Manager") !== -1;
	}

	function isUnlocked() {
		return sessionStorage.getItem(SESSION_KEY) === "1";
	}

	function showPinModal() {
		if (document.getElementById("sitiame-pin-overlay")) return;

		var overlay = document.createElement("div");
		overlay.id = "sitiame-pin-overlay";
		overlay.style.cssText =
			"position:fixed;inset:0;z-index:99999;background:rgba(15,23,42,.7);display:flex;align-items:center;justify-content:center;";
		overlay.innerHTML =
			"<div style='background:#fff;border-radius:14px;padding:28px;width:300px;max-width:90vw;text-align:center;box-shadow:0 10px 40px rgba(0,0,0,.3);'>" +
			"<div style='font-size:15px;font-weight:700;margin-bottom:6px;'>" + __("Acces protege") + "</div>" +
			"<div style='font-size:12px;color:#64748b;margin-bottom:16px;'>" + __("Entrez le code pour acceder a Club Sportif") + "</div>" +
			"<input id='sitiame-pin-input' type='password' inputmode='numeric' maxlength='6' style='width:100%;box-sizing:border-box;text-align:center;font-size:20px;letter-spacing:6px;padding:10px;border:1px solid #cbd5e1;border-radius:8px;margin-bottom:10px;'>" +
			"<div id='sitiame-pin-error' style='color:#dc2626;font-size:12px;min-height:16px;margin-bottom:10px;'></div>" +
			"<div style='display:flex;gap:8px;'>" +
			"<button id='sitiame-pin-cancel' style='flex:1;padding:9px;border-radius:8px;border:1px solid #cbd5e1;background:#fff;cursor:pointer;'>" + __("Annuler") + "</button>" +
			"<button id='sitiame-pin-submit' style='flex:1;padding:9px;border-radius:8px;border:none;background:#2563eb;color:#fff;cursor:pointer;'>" + __("Valider") + "</button>" +
			"</div></div>";
		document.body.appendChild(overlay);

		var input = overlay.querySelector("#sitiame-pin-input");
		var error = overlay.querySelector("#sitiame-pin-error");
		input.focus();

		function submit() {
			var pin = input.value.trim();
			if (!pin) return;
			frappe.call({ method: "sitiame_core.api.verify_club_sportif_pin", args: { pin: pin } }).then(function (r) {
				if (r.message && r.message.ok) {
					sessionStorage.setItem(SESSION_KEY, "1");
					overlay.remove();
				} else {
					error.textContent = __("Code incorrect.");
					input.value = "";
					input.focus();
				}
			});
		}

		overlay.querySelector("#sitiame-pin-submit").addEventListener("click", submit);
		input.addEventListener("keydown", function (e) {
			if (e.key === "Enter") submit();
		});
		overlay.querySelector("#sitiame-pin-cancel").addEventListener("click", function () {
			overlay.remove();
			frappe.set_route("/app");
		});
	}

	function guard() {
		if (isAdmin()) return;
		if (window.location.pathname.indexOf(LOCK_ROUTE_FRAGMENT) === -1) return;
		if (isUnlocked()) return;

		showPinModal();
	}

	$(document).on("app_ready", guard);
	$(document).on("page-change", function () {
		setTimeout(guard, 100);
	});
	document.addEventListener("DOMContentLoaded", function () {
		setTimeout(guard, 300);
	});
})();
