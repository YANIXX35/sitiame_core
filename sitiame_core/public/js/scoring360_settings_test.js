// Adds a "Tester sur une societe" button to the Scoring 360 Settings page,
// letting an admin sanity-check the configured thresholds/weights against
// a real Company's GL data without leaving the settings screen.
frappe.ui.form.on("Scoring 360 Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Tester sur une societe"), function () {
			var dialog = new frappe.ui.Dialog({
				title: __("Tester le scoring 360"),
				fields: [
					{ fieldname: "company", label: __("Societe"), fieldtype: "Link", options: "Company", reqd: 1 },
					{ fieldname: "date_from", label: __("Periode du"), fieldtype: "Date" },
					{ fieldname: "date_to", label: __("au"), fieldtype: "Date" },
				],
				primary_action_label: __("Calculer"),
				primary_action: function (values) {
					frappe.call({
						method: "sitiame_core.api.get_scoring360_score",
						args: { company: values.company, date_from: values.date_from, date_to: values.date_to },
					}).then(function (r) {
						var data = r.message || {};
						var blocks = data.blocks || {};
						var composite = data.composite || {};

						var rows = ["bank", "investor", "internal"].map(function (key) {
							var b = blocks[key] || {};
							var d = b.decision || {};
							return (
								"<tr><td>" + key + "</td><td>" + (b.total != null ? b.total : "-") +
								"</td><td>" + (d.label || "-") + "</td></tr>"
							);
						});

						var html =
							"<table class='table table-bordered'><thead><tr><th>" + __("Bloc") + "</th><th>" +
							__("Score") + "</th><th>" + __("Decision") + "</th></tr></thead><tbody>" +
							rows.join("") +
							"<tr class='fw-bold'><td>" + __("Composite") + "</td><td>" +
							(composite.total != null ? composite.total : "-") + "</td><td>" +
							(composite.decision ? composite.decision.label : "-") + "</td></tr>" +
							"</tbody></table>";

						frappe.msgprint({ title: __("Resultat du scoring"), indicator: "blue", message: html });
					});
				},
			});
			dialog.show();
		});
	},
});
