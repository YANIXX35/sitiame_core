// Copyright (c) 2026, Sitiame Capital
// License: MIT

frappe.ui.form.on("Subscription Payment", {
	refresh: function (frm) {
		if (frm.is_new()) return;

		if (!frm.doc.transaction_id) {
			frm.add_custom_button(__("Générer le lien de paiement"), function () {
				generate_payment_link(frm);
			});
		}

		if (frm.doc.payment_url) {
			frm.add_custom_button(__("Ouvrir le lien de paiement"), function () {
				window.open(frm.doc.payment_url, "_blank");
			});
		}
	},
});

function generate_payment_link(frm) {
	frappe.call({
		method: "sitiame_core.subscription_api.generate_subscription_payment_link",
		args: { docname: frm.doc.name },
		freeze: true,
		freeze_message: __("Génération du lien CinetPay..."),
	}).then(function () {
		frappe.show_alert({ message: __("Lien de paiement généré."), indicator: "green" });
		frm.reload_doc();
	});
}
