// Copyright (c) 2026, Sitiame Capital
// License: MIT

frappe.ui.form.on("Financing Dossier", {
	refresh: function (frm) {
		frm.add_custom_button(__("Synchroniser depuis PME360"), function () {
			financing_dossier_sync(frm);
		});

		// A chargé d'affaires proposes, a validator gives the opinion (the
		// server enforces it too: sitiame_core.portfolio.check_decision).
		if (frappe.user.has_role("Charge d'affaires Sitiame")
			&& !frappe.user.has_role("System Manager") && !frappe.user.has_role("Analyste Credit Sitiame")) {
			var proposals = ["A examiner", "En cours d'analyse"];
			if (!frm.doc.status || proposals.indexOf(frm.doc.status) !== -1) {
				frm.set_df_property("status", "options", proposals.join("\n"));
			} else {
				frm.set_df_property("status", "read_only", 1);
			}
			frm.set_df_property("status", "description", __("L'avis (favorable, défavorable, ajourné) revient à un validateur."));
		}

		if (!frm.doc.company) return;
	},

	company: function (frm) {
		if (frm.doc.company && frm.is_new()) {
			financing_dossier_sync(frm);
		}
	},
});

function financing_dossier_sync(frm) {
	if (!frm.doc.company) {
		frappe.msgprint(__("Choisissez d'abord une société."));
		return;
	}

	frappe.call({
		method: "sitiame_core.api.get_financing_dossier_from_pme360",
		args: { company: frm.doc.company },
		freeze: true,
		freeze_message: __("Récupération depuis PME360..."),
	}).then(function (r) {
		var data = r.message || {};

		if (data.status === "ignored") {
			frappe.show_alert({
				message: __("PME360 : ") + (data.reason || __("aucune donnée trouvée")),
				indicator: "orange",
			});
			return;
		}

		if (data.status !== "ok") {
			frappe.show_alert({ message: __("PME360 injoignable ou erreur."), indicator: "red" });
			return;
		}

		var fields = [
			"pme360_reference", "pme360_status", "financing_type", "financing_purpose",
			"amount_requested", "currency", "desired_term_months", "grace_period_months",
			"repayment_frequency", "promoter_contribution", "desired_disbursement_date",
			"financing_summary", "repayment_source",
		];
		var apiToDoctypeField = {
			reference: "pme360_reference",
			dossier_status: "pme360_status",
		};

		Object.keys(data).forEach(function (key) {
			var targetField = apiToDoctypeField[key] || key;
			if (fields.indexOf(targetField) !== -1) {
				frm.set_value(targetField, data[key]);
			}
		});

		frm.set_value("last_synced_at", frappe.datetime.now_datetime());
		frappe.show_alert({ message: __("Dossier synchronisé depuis PME360."), indicator: "green" });
	});
}
