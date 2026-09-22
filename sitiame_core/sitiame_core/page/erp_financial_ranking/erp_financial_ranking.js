frappe.pages["erp-financial-ranking"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Classement financier"),
		single_column: true,
	});

	var $filters = $(
		"<div class='row' style='padding:0 15px;margin-top:10px;'>" +
			"<div class='col-sm-3'><label class='control-label'>" + __("Periode du") + "</label>" +
			"<input type='date' class='form-control erp-fr-from'></div>" +
			"<div class='col-sm-3'><label class='control-label'>" + __("au") + "</label>" +
			"<input type='date' class='form-control erp-fr-to'></div>" +
			"<div class='col-sm-3' style='align-self:flex-end;'>" +
			"<button class='btn btn-primary erp-fr-refresh' style='margin-top:22px;'>" + __("Actualiser le classement") + "</button>" +
			"</div></div>"
	).appendTo(page.body);

	var $body = $("<div style='padding:0 15px;margin-top:15px;'></div>").appendTo(page.body);

	function statCard(label, value, colorClass) {
		return (
			"<div class='col-sm-3' style='margin-bottom:15px;'>" +
			"<div class='card' style='padding:15px;border-left:4px solid " + colorClass + ";'>" +
			"<div class='text-muted' style='font-size:12px;'>" + label + "</div>" +
			"<div style='font-size:24px;font-weight:600;'>" + value + "</div>" +
			"</div></div>"
		);
	}

	function render() {
		var args = {};
		var from = $filters.find(".erp-fr-from").val();
		var to = $filters.find(".erp-fr-to").val();
		if (from) args.date_from = from;
		if (to) args.date_to = to;

		$body.html("<p class='text-muted'>" + __("Calcul en cours...") + "</p>");

		frappe.call({ method: "sitiame_core.api.get_financial_ranking", args: args }).then(function (r) {
			var data = r.message || {};
			var lignes = data.lignes || [];
			var c = data.compteurs || {};

			var html = "<div class='row'>";
			html += statCard(__("Pret a deployer"), c.pret_a_deployer || 0, "#2b8a3e");
			html += statCard(__("Solide mais a cadrer"), c.solide_mais_a_cadrer || 0, "#e8a33d");
			html += statCard(__("Risque a traiter"), c.risque_a_traiter || 0, "#e03131");
			html += statCard(__("Donnees insuffisantes"), c.insuffisant || 0, "#868e96");
			html += "</div>";

			if (!lignes.length) {
				html += "<p class='text-muted'>" + __("Aucune societe a classer.") + "</p>";
			} else {
				html +=
					"<table class='table table-bordered bg-white'><thead><tr>" +
					"<th>" + __("Societe") + "</th>" +
					"<th class='text-end'>" + __("Ecritures") + "</th>" +
					"<th class='text-end'>" + __("Score composite") + "</th>" +
					"<th>" + __("Decision") + "</th>" +
					"<th class='text-end'>" + __("Contribution Banque") + "</th>" +
					"<th class='text-end'>" + __("Contribution Investisseur") + "</th>" +
					"<th class='text-end'>" + __("Contribution Interne") + "</th>" +
					"</tr></thead><tbody>";

				var badgeClass = { pret_a_deployer: "success", solide_mais_a_cadrer: "warning", risque_a_traiter: "danger" };

				lignes.forEach(function (row) {
					var decision = row.decision || {};
					var level = decision.level === "insuffisant" ? "insuffisant" :
						(decision.level === "strong" ? "pret_a_deployer" : decision.level === "medium" ? "solide_mais_a_cadrer" : "risque_a_traiter");
					var cls = badgeClass[level] || "light";
					var blocks = row.blocks || {};
					html +=
						"<tr>" +
						"<td class='fw-bold'>" + frappe.utils.escape_html(row.company_name || row.company) + "</td>" +
						"<td class='text-end'>" + row.entries_count + "</td>" +
						"<td class='text-end'>" + (row.composite_score !== null && row.composite_score !== undefined ? row.composite_score : "-") + "</td>" +
						"<td><span class='indicator-pill " + cls + "'>" + frappe.utils.escape_html(decision.label || "-") + "</span></td>" +
						"<td class='text-end'>" + (blocks.bank !== undefined && blocks.bank !== null ? blocks.bank : "-") + "</td>" +
						"<td class='text-end'>" + (blocks.investor !== undefined && blocks.investor !== null ? blocks.investor : "-") + "</td>" +
						"<td class='text-end'>" + (blocks.internal !== undefined && blocks.internal !== null ? blocks.internal : "-") + "</td>" +
						"</tr>";
				});

				html += "</tbody></table>";
			}

			$body.html(html);
		});
	}

	$filters.find(".erp-fr-refresh").on("click", render);

	render();
};
