frappe.pages["erp-caisse-banque"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Suivi des encaissements"),
		single_column: true,
	});

	var $filters = $(
		"<div class='row' style='padding:0 15px;margin-top:10px;'>" +
			"<div class='col-sm-2'><label class='control-label'>" + __("Statut") + "</label>" +
			"<select class='form-control erp-cb-bucket'>" +
			"<option value=''>" + __("Tous") + "</option>" +
			"<option value='unpaid'>" + __("Impaye") + "</option>" +
			"<option value='partial'>" + __("Partiel") + "</option>" +
			"<option value='paid'>" + __("Paye") + "</option>" +
			"</select></div>" +
			"<div class='col-sm-2'><label class='control-label'>" + __("Type") + "</label>" +
			"<select class='form-control erp-cb-type'>" +
			"<option value=''>" + __("Tous") + "</option>" +
			"<option value='Sales Invoice'>" + __("Facture de vente") + "</option>" +
			"<option value='Purchase Invoice'>" + __("Facture d'achat") + "</option>" +
			"</select></div>" +
			"<div class='col-sm-2'><label class='control-label'>" + __("Periode du") + "</label>" +
			"<input type='date' class='form-control erp-cb-from'></div>" +
			"<div class='col-sm-2'><label class='control-label'>" + __("au") + "</label>" +
			"<input type='date' class='form-control erp-cb-to'></div>" +
			"<div class='col-sm-2' style='align-self:flex-end;'>" +
			"<button class='btn btn-primary erp-cb-refresh' style='margin-top:22px;width:100%;'>" + __("Filtrer") + "</button>" +
			"</div></div>"
	).appendTo(page.body);

	var $body = $("<div style='padding:0 15px;margin-top:15px;'></div>").appendTo(page.body);

	function statCard(label, value, color) {
		return (
			"<div class='col-sm-4' style='margin-bottom:15px;'>" +
			"<div class='card' style='padding:15px;border-left:4px solid " + color + ";'>" +
			"<div class='text-muted' style='font-size:12px;'>" + label + "</div>" +
			"<div style='font-size:22px;font-weight:600;'>" + frappe.format(value, { fieldtype: "Currency" }) + "</div>" +
			"</div></div>"
		);
	}

	function render() {
		var args = {
			bucket: $filters.find(".erp-cb-bucket").val() || undefined,
			document_type: $filters.find(".erp-cb-type").val() || undefined,
			date_from: $filters.find(".erp-cb-from").val() || undefined,
			date_to: $filters.find(".erp-cb-to").val() || undefined,
		};

		$body.html("<p class='text-muted'>" + __("Chargement...") + "</p>");

		frappe.call({ method: "sitiame_core.api.list_caisse_banque", args: args }).then(function (r) {
			var data = r.message || {};
			var rows = data.rows || [];
			var totals = data.totals || {};

			var html = "<div class='row'>";
			html += statCard(__("Total impaye"), totals.unpaid, "#d1382c");
			html += statCard(__("Total partiel"), totals.partial, "#e8a33d");
			html += statCard(__("Total paye"), totals.paid, "#2b8a3e");
			html += "</div>";

			if (!rows.length) {
				html += "<p class='text-muted'>" + __("Aucune facture trouvee.") + "</p>";
			} else {
				html +=
					"<table class='table table-bordered bg-white'><thead><tr>" +
					"<th>" + __("Date") + "</th>" +
					"<th>" + __("Type") + "</th>" +
					"<th>" + __("Societe") + "</th>" +
					"<th>" + __("Client / Fournisseur") + "</th>" +
					"<th class='text-end'>" + __("Montant") + "</th>" +
					"<th class='text-end'>" + __("Solde du") + "</th>" +
					"<th>" + __("Statut") + "</th>" +
					"<th></th>" +
					"</tr></thead><tbody>";

				var bucketColor = { unpaid: "red", partial: "orange", paid: "green" };
				var typeRoute = { "Sales Invoice": "sales-invoice", "Purchase Invoice": "purchase-invoice" };

				rows.forEach(function (row) {
					html +=
						"<tr>" +
						"<td>" + frappe.datetime.str_to_user(row.posting_date) + "</td>" +
						"<td>" + (row.document_type === "Sales Invoice" ? __("Vente") : __("Achat")) + "</td>" +
						"<td>" + frappe.utils.escape_html(row.company || "") + "</td>" +
						"<td>" + frappe.utils.escape_html(row.party_name || "") + "</td>" +
						"<td class='text-end'>" + frappe.format(row.amount, { fieldtype: "Currency" }) + "</td>" +
						"<td class='text-end'>" + frappe.format(row.outstanding, { fieldtype: "Currency" }) + "</td>" +
						"<td><span class='indicator-pill " + (bucketColor[row.bucket] || "grey") + "'>" +
						frappe.utils.escape_html(row.status) + "</span></td>" +
						"<td><a class='btn btn-xs btn-default' href='/app/" + typeRoute[row.document_type] +
						"/" + encodeURIComponent(row.name) + "'>" + __("Ouvrir") + "</a></td>" +
						"</tr>";
				});

				html += "</tbody></table>";
			}

			$body.html(html);
		});
	}

	$filters.find(".erp-cb-refresh").on("click", render);

	render();
};
