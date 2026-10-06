// Copyright (c) 2026, Sitiame Capital
// License: MIT

// Espace comptable : liste toutes les PME actives, permet d'ouvrir
// la comptabilité de chacune et d'y créer des écritures directement.
frappe.pages["erp-comptable"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Portefeuille Comptable"),
		single_column: true,
	});
	page.set_secondary_action(__("Actualiser"), load, "refresh");

	var esc = frappe.utils.escape_html;
	var $body = $("<div style='padding: 0 15px 30px;'></div>").appendTo(page.body);

	var SUB_COLORS = { Actif: "green", Essai: "orange", "Expiré": "red", Aucun: "gray" };

	function subState(sub) {
		if (!sub) return "Aucun";
		if (sub.active) return "Actif";
		if (sub.in_trial) return "Essai";
		return sub.ends_on ? "Expiré" : "Aucun";
	}

	function pill(text, color) {
		return "<span class='indicator-pill " + (color || "gray") + "'>" + esc(text) + "</span>";
	}

	// Bascule la société par défaut de l'utilisateur puis navigue.
	function openCompany(company, route) {
		frappe.call({
			method: "frappe.client.set_value",
			args: {
				doctype: "User",
				name: frappe.session.user,
				fieldname: "simultaneous_sessions",
				value: frappe.defaults.get_user_default("simultaneous_sessions") || 1,
			},
			async: false,
		});
		frappe.defaults.update_user_default("company", company);
		frappe.set_route(route || "Accounting");
	}

	function exportLiasse(company) {
		var today = frappe.datetime.get_today();
		var year = today.slice(0, 4);
		var d = new frappe.ui.Dialog({
			title: __("Exporter Liasse SYSCOHADA"),
			fields: [
				{
					label: __("Société"),
					fieldname: "company",
					fieldtype: "Data",
					read_only: 1,
					default: company,
				},
				{
					label: __("Du"),
					fieldname: "from_date",
					fieldtype: "Date",
					reqd: 1,
					default: year + "-01-01",
				},
				{
					label: __("Au"),
					fieldname: "to_date",
					fieldtype: "Date",
					reqd: 1,
					default: today,
				},
			],
			primary_action_label: __("Télécharger"),
			primary_action: function (values) {
				d.hide();
				var url = "/api/method/sitiame_core.liasse_export.export_liasse" +
					"?company=" + encodeURIComponent(values.company) +
					"&from_date=" + encodeURIComponent(values.from_date) +
					"&to_date=" + encodeURIComponent(values.to_date);
				window.open(url, "_blank");
			},
		});
		d.show();
	}

	function buildTable(rows) {
		if (!rows.length) {
			return "<p class='text-muted'>" + __("Aucune société PME trouvée.") + "</p>";
		}
		var html = "<div style='overflow-x:auto'><table class='table table-bordered' style='font-size:13px;margin:0;min-width:720px'>" +
			"<thead><tr>" +
			"<th>" + __("Société") + "</th>" +
			"<th>" + __("Abonnement") + "</th>" +
			"<th>" + __("Dernière écriture") + "</th>" +
			"<th>" + __("Actions") + "</th>" +
			"</tr></thead><tbody>";

		rows.forEach(function (row, i) {
			var state = subState(row.subscription);
			var lastEntry = row.last_entry
				? frappe.datetime.str_to_user(row.last_entry)
				: "<span class='text-muted'>—</span>";
			html += "<tr>" +
				"<td><b>" + esc(row.company_name || row.company) + "</b>" +
				"<br><span class='text-muted small'>" + esc(row.company) + "</span></td>" +
				"<td>" + pill(__(state), SUB_COLORS[state]) + "</td>" +
				"<td>" + lastEntry + "</td>" +
				"<td style='white-space:nowrap'>" +
					"<button class='btn btn-xs btn-primary cp-open' data-i='" + i + "' style='margin-right:4px'>" +
						__("Ouvrir comptabilité") +
					"</button>" +
					"<button class='btn btn-xs btn-default cp-entry' data-i='" + i + "' style='margin-right:4px'>" +
						__("Nouvelle écriture") +
					"</button>" +
					"<button class='btn btn-xs btn-default cp-balance' data-i='" + i + "' style='margin-right:4px'>" +
						__("Balance") +
					"</button>" +
					"<button class='btn btn-xs btn-default cp-gl' data-i='" + i + "' style='margin-right:4px'>" +
						__("Grand livre") +
					"</button>" +
					"<button class='btn btn-xs btn-success cp-liasse' data-i='" + i + "'>" +
						__("Liasse SYSCOHADA") +
					"</button>" +
				"</td></tr>";
		});
		return html + "</tbody></table></div>";
	}

	function load() {
		$body.html("<p class='text-muted'>" + __("Chargement...") + "</p>");
		frappe.call({
			method: "sitiame_core.comptable.get_comptable_dashboard",
		}).then(function (r) {
			var rows = r.message || [];
			$body.html(
				"<div style='background:var(--card-bg,#fff);border:1px solid var(--border-color);border-radius:12px;padding:16px 18px;margin-bottom:18px'>" +
				"<h5 style='font-weight:700;margin:0 0 12px'>" +
				__("Sociétés") + " <span class='text-muted' style='font-weight:400'>(" + rows.length + ")</span>" +
				"</h5>" +
				buildTable(rows) +
				"</div>"
			);

			$body.find(".cp-open").on("click", function () {
				openCompany(rows[$(this).data("i")].company, "Accounting");
			});
			$body.find(".cp-entry").on("click", function () {
				var company = rows[$(this).data("i")].company;
				frappe.defaults.update_user_default("company", company);
				frappe.new_doc("Journal Entry", { company: company });
			});
			$body.find(".cp-balance").on("click", function () {
				var company = rows[$(this).data("i")].company;
				frappe.defaults.update_user_default("company", company);
				frappe.set_route("query-report", "Trial Balance", { company: company });
			});
			$body.find(".cp-gl").on("click", function () {
				var company = rows[$(this).data("i")].company;
				frappe.defaults.update_user_default("company", company);
				frappe.set_route("query-report", "General Ledger", { company: company });
			});
			$body.find(".cp-liasse").on("click", function () {
				exportLiasse(rows[$(this).data("i")].company);
			});
		});
	}

	load();
};
