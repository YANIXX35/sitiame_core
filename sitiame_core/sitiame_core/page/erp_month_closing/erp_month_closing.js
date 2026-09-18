frappe.pages["erp-month-closing"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Cloture mensuelle"),
		single_column: true,
	});

	var today = frappe.datetime.get_today();
	var defaultYm = today.slice(0, 7);

	var $filters = $(
		"<div class='row' style='padding:0 15px;margin-top:10px;'>" +
			"<div class='col-sm-4'><label class='control-label'>" + __("Societe") + "</label>" +
			"<input class='form-control erp-mc-company' placeholder='" + __("ex. SITIAME") + "'></div>" +
			"<div class='col-sm-3'><label class='control-label'>" + __("Mois") + "</label>" +
			"<input type='month' class='form-control erp-mc-month' value='" + defaultYm + "'></div>" +
			"<div class='col-sm-3' style='align-self:flex-end;'>" +
			"<button class='btn btn-primary erp-mc-refresh' style='margin-top:22px;width:100%;'>" + __("Verifier") + "</button>" +
			"</div></div>"
	).appendTo(page.body);

	var $body = $("<div style='padding:0 15px;margin-top:15px;'></div>").appendTo(page.body);

	function checkRow(ok, label, detail) {
		return (
			"<div style='padding:8px 0;border-bottom:1px solid var(--border-color);'>" +
			"<span class='indicator-pill " + (ok ? "green" : "orange") + "'>" + (ok ? __("OK") : __("A verifier")) + "</span> " +
			"<b>" + label + "</b> - " + detail +
			"</div>"
		);
	}

	function render() {
		var company = $filters.find(".erp-mc-company").val();
		var month = $filters.find(".erp-mc-month").val();

		if (!company || !month) {
			$body.html("<p class='text-muted'>" + __("Renseigne une societe et un mois.") + "</p>");
			return;
		}

		$body.html("<p class='text-muted'>" + __("Chargement...") + "</p>");

		frappe.call({
			method: "sitiame_core.api.get_month_closing_status",
			args: { company: company, year_month: month },
		}).then(function (r) {
			var data = r.message || {};

			var html = "<h5>" + frappe.utils.escape_html(company) + " - " + data.year_month + "</h5>";

			html += checkRow(
				data.check_journal,
				__("Journal"),
				data.entries_count + " " + __("ecriture(s) comptabilisee(s) sur le mois")
			);
			html += checkRow(
				data.check_payments,
				__("Paiements"),
				data.payments_count + " " + __("paiement(s) enregistre(s) sur le mois")
			);

			html += "<div style='margin-top:15px;'>";
			html +=
				"<a class='btn btn-default btn-sm' target='_blank' href='/app/query-report/General Ledger?company=" +
				encodeURIComponent(company) + "&from_date=" + data.start + "&to_date=" + data.end + "'>" +
				__("Ouvrir le Grand livre") + "</a> ";
			html +=
				"<a class='btn btn-default btn-sm' target='_blank' href='/app/query-report/Trial Balance?company=" +
				encodeURIComponent(company) + "'>" + __("Ouvrir la Balance") + "</a> ";
			html +=
				"<a class='btn btn-default btn-sm' target='_blank' href='/app/bank-reconciliation-tool?company=" +
				encodeURIComponent(company) + "'>" + __("Rapprochement bancaire") + "</a>";
			html += "</div>";

			if (data.closure) {
				html +=
					"<div class='alert alert-success' style='margin-top:15px;'>" +
					__("Mois deja cloture le") + " " + frappe.datetime.str_to_user(data.closure.closed_at) +
					" " + __("par") + " " + frappe.utils.escape_html(data.closure.closed_by) +
					(data.closure.notes ? "<br>" + frappe.utils.escape_html(data.closure.notes) : "") +
					"</div>";
			}

			html +=
				"<div style='margin-top:15px;'>" +
				"<textarea class='form-control erp-mc-notes' rows='2' placeholder='" + __("Notes (optionnel)") + "'></textarea>" +
				"<button class='btn btn-primary erp-mc-close' style='margin-top:10px;'>" + __("Cloturer le mois") + "</button>" +
				"</div>";

			$body.html(html);

			$body.find(".erp-mc-close").on("click", function () {
				frappe.confirm(
					__("Marquer {0} comme cloture pour {1} ? Ceci n'empeche pas de nouvelles ecritures -- c'est un repere de suivi.", [data.year_month, company]),
					function () {
						frappe.call({
							method: "sitiame_core.api.close_month",
							args: { company: company, year_month: data.year_month, notes: $body.find(".erp-mc-notes").val() },
						}).then(function () {
							frappe.show_alert({ message: __("Mois cloture."), indicator: "green" });
							render();
						});
					}
				);
			});
		});
	}

	$filters.find(".erp-mc-refresh").on("click", render);
};
