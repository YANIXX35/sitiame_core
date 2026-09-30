// Copyright (c) 2026, Sitiame Capital
// License: MIT

// Abonnement SITIAME: a PME sees its subscription state; Sitiame staff see
// every PME's. Online payment comes with the Jèko integration.
frappe.pages["erp-abonnement"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Abonnement SITIAME"),
		single_column: true,
	});

	var esc = frappe.utils.escape_html;

	function dateText(value) {
		return value ? frappe.datetime.str_to_user(value) : "-";
	}

	frappe.call({ method: "sitiame_core.subscription_api.get_my_subscription" }).then(function (r) {
		var sub = r.message || {};
		var staff = frappe.user.has_role("System Manager") || frappe.user.has_role("Charge d'affaires Sitiame");
		if (!sub.company && staff) {
			renderStaffPanel();
		} else if (!sub.company) {
			renderCard(
				"<div style='color: #b91c1c;'>" +
				__("Cette page est réservée aux comptes PME : aucune société n'est rattachée à votre compte.") +
				"</div>"
			);
		} else {
			renderPmeState(sub);
		}
	});

	function renderCard(inner) {
		$(
			"<div style='max-width: 580px; margin: 30px auto; padding: 35px 25px; background: var(--card-bg, #fff); border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.06); text-align: center;'>" +
				"<h3 style='font-weight: 700; margin-bottom: 6px; font-size: 22px;'>" + __("Abonnement SITIAME CAPITAL") + "</h3>" +
				"<p style='color: #64748b; font-size: 14px; margin-bottom: 25px;'>" + __("Pack Premium Enterprise : <strong>15 000 FCFA</strong> / mois") + "</p>" +
				inner +
			"</div>"
		).appendTo(page.body);
	}

	// A PME: where its subscription stands. The pay button comes back with Jèko.
	function renderPmeState(sub) {
		var state;
		if (sub.active) {
			state = "<div style='font-size: 20px; font-weight: 700; color: #15803d; margin-bottom: 8px;'>" + __("Abonnement actif") + "</div>" +
				"<div style='font-size: 14px; color: #475569;'>" + __("Actif jusqu'au <strong>{0}</strong>.", [dateText(sub.ends_on)]) + "</div>";
		} else if (sub.in_trial) {
			state = "<div style='font-size: 20px; font-weight: 700; color: #b45309; margin-bottom: 8px;'>" + __("Période d'essai") + "</div>" +
				"<div style='font-size: 14px; color: #475569;'>" + __("Essai gratuit jusqu'au <strong>{0}</strong>.", [dateText(sub.trial_ends_on)]) + "</div>";
		} else {
			state = "<div style='font-size: 20px; font-weight: 700; color: #991b1b; margin-bottom: 8px;'>" + __("Aucun abonnement actif") + "</div>" +
				(sub.ends_on ? "<div style='font-size: 14px; color: #475569;'>" + __("Expiré le {0}.", [dateText(sub.ends_on)]) + "</div>" : "");
		}
		renderCard(
			state +
			"<div style='margin-top: 22px; padding: 12px; background: #f8fafc; border-radius: 10px; font-size: 13px; color: #64748b;'>" +
				__("Le paiement en ligne sera bientôt disponible. En attendant, contactez votre chargé d'affaires SITIAME pour renouveler votre abonnement.") +
			"</div>"
		);
	}

	// Sitiame staff: every PME's subscription state.
	function renderStaffPanel() {
		var $admin = $(
			"<div style='max-width: 1000px; margin: 24px auto; padding: 0 16px;'>" +
				"<div style='background: var(--card-bg, #fff); border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); padding: 20px 22px;'>" +
					"<h4 style='font-weight: 700; margin: 0 0 12px;'>" + __("Abonnements des PME") + "</h4>" +
					"<div class='admin-subscriptions' style='overflow-x: auto;'>" + __("Chargement...") + "</div>" +
				"</div>" +
			"</div>"
		).appendTo(page.body);

		var STATE_COLORS = { "Actif": "green", "Essai": "orange", "Expiré": "red", "Aucun": "gray" };

		frappe.call({ method: "sitiame_core.subscription_api.list_company_subscriptions" }).then(function (r) {
			var rows = r.message || [];
			if (!rows.length) {
				$admin.find(".admin-subscriptions").html("<p style='color: #64748b;'>" + __("Aucune PME.") + "</p>");
				return;
			}
			var html = "<table class='table table-bordered' style='font-size: 13px; margin: 0;'><thead><tr>" +
				"<th>" + __("Société") + "</th><th>" + __("Statut") + "</th><th>" + __("Actif jusqu'au") + "</th>" +
				"<th>" + __("Fin d'essai") + "</th><th>" + __("Paiements") + "</th><th>" + __("Dernier paiement") + "</th>" +
				"</tr></thead><tbody>";
			rows.forEach(function (row) {
				html += "<tr>" +
					"<td>" + esc(row.company) + "</td>" +
					"<td><span class='indicator-pill " + (STATE_COLORS[row.state] || "gray") + "'>" + __(row.state) + "</span></td>" +
					"<td>" + dateText(row.ends_on) + "</td>" +
					"<td>" + dateText(row.trial_ends_on) + "</td>" +
					"<td>" + row.paid_count + "</td>" +
					"<td>" + (row.last_paid_at ? frappe.datetime.str_to_user(row.last_paid_at) : "-") + "</td>" +
					"</tr>";
			});
			html += "</tbody></table>";
			$admin.find(".admin-subscriptions").html(html);
		});
	}
};
