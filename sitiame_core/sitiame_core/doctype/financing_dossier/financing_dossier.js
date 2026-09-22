// Copyright (c) 2026, Sitiame Capital
// License: MIT

frappe.ui.form.on("Financing Dossier", {
	refresh: function (frm) {
		frm.add_custom_button(__("Synchroniser depuis PME360"), function () {
			financing_dossier_sync(frm);
		});

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
