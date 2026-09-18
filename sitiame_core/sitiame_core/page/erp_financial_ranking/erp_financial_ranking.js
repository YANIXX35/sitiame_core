frappe.pages["erp-financial-ranking"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Classement financier ERPNext"),
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
			html += statCard(__("Financables"), c.financable || 0, "#2b8a3e");
			html += statCard(__("Solvables seulement"), c.solvable_seulement || 0, "#e8a33d");
			html += statCard(__("Non retenus"), c.non_retenu || 0, "#868e96");
			html += statCard(__("Donnees insuffisantes"), c.insuffisant || 0, "#868e96");
			html += "</div>";

			html +=
				"<div class='alert alert-secondary small'>" +
				"<strong>" + __("Solvable") + "</strong> " + __("- au moins 5 ecritures et verdict de solvabilite favorable ou score >= 54/100.") +
				"<br><strong>" + __("Financable") + "</strong> " + __("- profil solvable + au moins 15 ecritures + rentabilite favorable + fiabilite des donnees >= 52% + synthese fiabilisee >= 48/100.") +
				"</div>";

			if (!lignes.length) {
				html += "<p class='text-muted'>" + __("Aucune societe a classer.") + "</p>";
			} else {
				html +=
					"<table class='table table-bordered bg-white'><thead><tr>" +
					"<th>" + __("Societe") + "</th>" +
					"<th class='text-end'>" + __("Ecritures") + "</th>" +
					"<th>" + __("Categorie") + "</th>" +
					"<th class='text-center'>" + __("Solvable") + "</th>" +
					"<th class='text-center'>" + __("Financable") + "</th>" +
					"<th class='text-end'>" + __("Synthese fiabilisee") + "</th>" +
					"<th>" + __("Motifs") + "</th>" +
					"</tr></thead><tbody>";

				var badgeClass = { financable: "success", solvable_seulement: "warning", non_retenu: "secondary" };

				lignes.forEach(function (row) {
					var cl = row.classement || {};
					var code = cl.code || "insuffisant";
					var cls = badgeClass[code] || "light";
					var motifs = (cl.motifs || []).slice(0, 3);
					html +=
						"<tr>" +
						"<td class='fw-bold'>" + frappe.utils.escape_html(row.company_name || row.company) + "</td>" +
						"<td class='text-end'>" + row.entries_count + "</td>" +
						"<td><span class='indicator-pill " + cls + "'>" + frappe.utils.escape_html(cl.libelle || "-") + "</span></td>" +
						"<td class='text-center'>" + (cl.solvable ? "<span class='text-success'>Oui</span>" : "<span class='text-muted'>Non</span>") + "</td>" +
						"<td class='text-center'>" + (cl.financable ? "<span class='text-success fw-bold'>Oui</span>" : "<span class='text-muted'>Non</span>") + "</td>" +
						"<td class='text-end'>" + (row.synthese_fiabilisee !== null && row.synthese_fiabilisee !== undefined ? row.synthese_fiabilisee : "-") + "</td>" +
						"<td class='small text-muted'>" + motifs.map(frappe.utils.escape_html).join("<br>") + "</td>" +
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
