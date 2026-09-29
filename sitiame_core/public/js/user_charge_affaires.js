// Copyright (c) 2026, Sitiame Capital
// License: MIT

// User form: turn a staff account into a chargé d'affaires in one click
// (role + only his tiles on the home screen). sitiame_core.portfolio.
frappe.ui.form.on("User", {
	refresh: function (frm) {
		if (frm.is_new() || !frappe.user.has_role("System Manager") || frm.doc.user_type !== "System User") return;
		frm.add_custom_button(__("Configurer comme chargé d'affaires"), function () {
			frappe.confirm(
				__("Donner le rôle « Charge d'affaires Sitiame » à {0} et masquer tous ses autres modules (il gardera : Chargé d'affaires, CRM, Scoring, Financement) ?", [frm.doc.full_name || frm.doc.name]),
				function () {
					frappe.call({
						method: "sitiame_core.portfolio.configure_charge_affaires",
						args: { user: frm.doc.name },
						freeze: true,
					}).then(function () {
						frappe.msgprint(__("Compte configuré. Attribuez-lui ses PME dans le champ « Chargé d'affaires » de chaque fiche Société ; il doit se reconnecter."));
						frm.reload_doc();
					});
				}
			);
		}, __("Sitiame"));
	},
});
