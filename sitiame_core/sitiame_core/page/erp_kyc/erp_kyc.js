frappe.pages["erp-kyc"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Documents KYC"),
		single_column: true,
	});

	var $intro = $(
		"<p class='text-muted' style='padding:0 15px;'>" +
			__(
				"PME360 pousse automatiquement les documents KYC/KYB approuves de chaque client vers la fiche Societe correspondante dans ERPNext. Cette page les regroupe par societe."
			) +
			"</p>"
	).appendTo(page.body);

	var $body = $("<div style='padding:0 15px;'></div>").appendTo(page.body);

	function render() {
		$body.html("<p class='text-muted'>" + __("Chargement...") + "</p>");

		frappe.call({ method: "sitiame_core.api.list_erp_kyc_documents" }).then(function (r) {
			var data = r.message || {};
			var groups = data.groups || [];

			var html =
				"<p><span class='indicator-pill blue'>" +
				(data.total_documents || 0) +
				" " + __("document(s)") + "</span> " +
				"<span class='indicator-pill grey'>" +
				(data.total_companies_with_documents || 0) +
				" " + __("societe(s)") + "</span></p>";

			if (!groups.length) {
				html += "<p class='text-muted'>" + __("Aucun document KYC synchronise pour le moment.") + "</p>";
			} else {
				groups.forEach(function (group) {
					html += "<h6 style='margin-top:15px;'>" + frappe.utils.escape_html(group.company_name) + "</h6>";
					html +=
						"<table class='table table-bordered bg-white'><thead><tr>" +
						"<th>" + __("Fichier") + "</th><th>" + __("Taille") + "</th><th>" + __("Ajoute le") + "</th><th></th>" +
						"</tr></thead><tbody>";
					group.documents.forEach(function (doc) {
						html +=
							"<tr>" +
							"<td>" + frappe.utils.escape_html(doc.file_name) + "</td>" +
							"<td>" + doc.size_kb + " Ko</td>" +
							"<td>" + doc.created_at + "</td>" +
							"<td><a class='btn btn-xs btn-default' target='_blank' href='" + doc.file_url + "'>" +
							__("Ouvrir") + "</a></td>" +
							"</tr>";
					});
					html += "</tbody></table>";
				});
			}

			$body.html(html);
		});
	}

	render();
};
