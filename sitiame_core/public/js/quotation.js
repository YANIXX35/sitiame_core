// Copyright (c) 2026, Sitiame Capital
// License: MIT

// "Modifier le devis" on a validated quotation: cancels it and opens its new
// draft version in one step (sitiame_core/quotation.py), the ERPNext way to
// change a validated document.
frappe.ui.form.on("Quotation", {
	refresh: function (frm) {
		if (frm.doc.docstatus !== 1 || ["Ordered", "Partially Ordered"].includes(frm.doc.status)) return;
		if (!frappe.model.can_cancel("Quotation") || !frappe.model.can_create("Quotation")) return;

		frm.add_custom_button(__("Modifier le devis"), function () {
			frappe.confirm(
				__("Un devis validé ne se modifie pas directement. Le devis {0} va être annulé et une nouvelle version en brouillon va être créée : vous pourrez la modifier puis la valider. Continuer ?", [frm.doc.name]),
				function () {
					frappe.call({
						method: "sitiame_core.quotation.amend_quotation",
						args: { name: frm.doc.name },
						freeze: true,
						freeze_message: __("Création de la nouvelle version..."),
					}).then(function (r) {
						if (!r.message) return;
						frappe.show_alert({ message: __("Nouvelle version {0} créée : vous pouvez la modifier.", [r.message]), indicator: "green" });
						frappe.set_route("Form", "Quotation", r.message);
					});
				}
			);
		});
	},
});
