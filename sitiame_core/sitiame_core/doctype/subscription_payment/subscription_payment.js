// Copyright (c) 2026, Sitiame Capital
// License: MIT

frappe.ui.form.on("Subscription Payment", {
	refresh: function (frm) {
		if (frm.is_new()) return;

		if (frm.doc.payment_url) {
			frm.add_custom_button(__("Ouvrir le lien de paiement"), function () {
				window.open(frm.doc.payment_url, "_blank");
			});
		}
	},
});
