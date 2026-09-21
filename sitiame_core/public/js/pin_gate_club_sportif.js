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
	// Deliberately in-memory only (not sessionStorage): the unlock must
	// NOT survive a page reload or leaving Club Sportif and coming back --
	// it only holds while navigating between Club Sportif's own pages
	// (Membres/Cotisations/Evenements) without leaving that context.
	var unlocked = false;

	function isAdmin() {
		var roles = (frappe.boot && frappe.boot.user && frappe.boot.user.roles) || [];
		return roles.indexOf("System Manager") !== -1 || roles.indexOf("Workspace Manager") !== -1;
	}

	// The URL alone isn't enough: clicking "Membres" inside the Club
	// Sportif workspace navigates straight to /app/customer, which never
	// contains "club-sportif" in the path. An earlier version tried to
	// work around this by scanning the DOM for a persistent "Club Sportif"
	// sidebar label -- but that label is also present (lower down) in the
	// normal desk sidebar on EVERY page for any user who can see more than
	// one workspace, which made the PIN pop up on totally unrelated pages
	// like /desk/invoicing. Track the actual workspace instead: remember
	// the last *real* workspace route the user landed on (using Frappe's
	// own workspace list + its own slug function, not a guess), and keep
	// that as "current workspace" through any sub-navigation that isn't
	// itself a workspace route (e.g. clicking into Customer/Subscription/
	// Event from within Club Sportif).
	var lastWorkspaceSlug = null;
	var workspaceSlugs = null;

	function buildWorkspaceSlugMap() {
		var map = {};
		var workspaces = (frappe.workspaces) || {};
		Object.keys(workspaces).forEach(function (name) {
			try {
				map[frappe.router.slug(name)] = name;
			} catch (e) {
				/* ignore, this workspace just won't be recognised */
			}
		});
		return map;
	}

	function updateWorkspaceContext() {
		// Rebuild if we never got a map, or frappe.workspaces wasn't
		// populated yet on the very first call (boot ordering).
		if (!workspaceSlugs || Object.keys(workspaceSlugs).length === 0) {
			workspaceSlugs = buildWorkspaceSlugMap();
		}

		var route = frappe.get_route();
		var slug = route && route[0] && String(route[0]).toLowerCase();
		if (slug && Object.prototype.hasOwnProperty.call(workspaceSlugs, slug)) {
			lastWorkspaceSlug = slug;
		}
	}

	function clubSportifContextActive() {
		updateWorkspaceContext();
		return lastWorkspaceSlug === "club-sportif";
	}

	function showPinModal() {
		if (document.getElementById("sitiame-pin-overlay")) return;

		var overlay = document.createElement("div");
		overlay.id = "sitiame-pin-overlay";
		overlay.style.cssText =
			"position:fixed;inset:0;z-index:99999;background:#0f172a;display:flex;align-items:center;justify-content:center;";
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
					unlocked = true;
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

		if (!clubSportifContextActive()) {
			// Left Club Sportif: forget the unlock so coming back re-prompts.
			unlocked = false;
			return;
		}

		if (unlocked) return;
		showPinModal();
	}

	$(document).on("app_ready", guard);
	$(document).on("page-change", function () {
		setTimeout(guard, 100);
		setTimeout(guard, 400);
		setTimeout(guard, 900);
	});
	document.addEventListener("DOMContentLoaded", function () {
		setTimeout(guard, 300);
	});
})();
