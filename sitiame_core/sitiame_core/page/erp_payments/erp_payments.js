frappe.pages["erp-payments"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Paiements"),
		single_column: true,
	});

	var $filters = $(
		"<div class='row' style='padding:0 15px;margin-top:10px;'>" +
			"<div class='col-sm-2'><label class='control-label'>" + __("Societe") + "</label>" +
			"<input class='form-control erp-pay-company' placeholder='" + __("ex. SITIAME") + "'></div>" +
			"<div class='col-sm-2'><label class='control-label'>" + __("Client/Fournisseur") + "</label>" +
			"<input class='form-control erp-pay-party'></div>" +
			"<div class='col-sm-2'><label class='control-label'>" + __("Statut") + "</label>" +
			"<select class='form-control erp-pay-status'>" +
			"<option value=''>" + __("Tous") + "</option>" +
			"<option value='Draft'>Draft</option>" +
			"<option value='Submitted'>Submitted</option>" +
			"<option value='Cancelled'>Cancelled</option>" +
			"</select></div>" +
			"<div class='col-sm-2'><label class='control-label'>" + __("Periode du") + "</label>" +
			"<input type='date' class='form-control erp-pay-from'></div>" +
			"<div class='col-sm-2'><label class='control-label'>" + __("au") + "</label>" +
			"<input type='date' class='form-control erp-pay-to'></div>" +
			"<div class='col-sm-2' style='align-self:flex-end;'>" +
			"<button class='btn btn-primary erp-pay-refresh' style='margin-top:22px;width:100%;'>" + __("Filtrer") + "</button>" +
			"</div></div>"
	).appendTo(page.body);

	var $body = $("<div style='padding:0 15px;margin-top:15px;'></div>").appendTo(page.body);

	function statCard(label, value) {
		return (
			"<div class='col-sm-4' style='margin-bottom:15px;'>" +
			"<div class='card' style='padding:15px;'>" +
			"<div class='text-muted' style='font-size:12px;'>" + label + "</div>" +
			"<div style='font-size:22px;font-weight:600;'>" + value + "</div>" +
			"</div></div>"
		);
	}

	function fmtMoney(v) {
		return frappe.format(v || 0, { fieldtype: "Currency" });
	}

	function render() {
		var args = {
			company: $filters.find(".erp-pay-company").val() || undefined,
			party: $filters.find(".erp-pay-party").val() || undefined,
			status: $filters.find(".erp-pay-status").val() || undefined,
			date_from: $filters.find(".erp-pay-from").val() || undefined,
			date_to: $filters.find(".erp-pay-to").val() || undefined,
		};

		$body.html("<p class='text-muted'>" + __("Chargement...") + "</p>");

		frappe.call({ method: "sitiame_core.api.list_erp_payments", args: args }).then(function (r) {
			var data = r.message || {};
			var rows = data.rows || [];
			var summary = data.summary || {};

			var html = "<div class='row'>";
			html += statCard(__("Transactions"), summary.count || 0);
			html += statCard(__("Total encaisse"), fmtMoney(summary.received_total));
			html += statCard(__("Total decaisse"), fmtMoney(summary.paid_total));
			html += "</div>";

			if (!rows.length) {
				html += "<p class='text-muted'>" + __("Aucun paiement trouve.") + "</p>";
			} else {
				html +=
					"<table class='table table-bordered bg-white'><thead><tr>" +
					"<th>" + __("Date") + "</th>" +
					"<th>" + __("Societe") + "</th>" +
					"<th>" + __("Type") + "</th>" +
					"<th>" + __("Client / Fournisseur") + "</th>" +
					"<th class='text-end'>" + __("Montant") + "</th>" +
					"<th>" + __("Mode") + "</th>" +
					"<th>" + __("Reference") + "</th>" +
					"<th>" + __("Statut") + "</th>" +
					"<th></th>" +
					"</tr></thead><tbody>";

				rows.forEach(function (row) {
					var amount = row.payment_type === "Receive" ? row.received_amount : row.paid_amount;
					var statusClass = row.status === "Submitted" ? "green" : row.status === "Cancelled" ? "red" : "orange";
					html +=
						"<tr>" +
						"<td>" + frappe.datetime.str_to_user(row.posting_date) + "</td>" +
						"<td>" + frappe.utils.escape_html(row.company || "") + "</td>" +
						"<td>" + frappe.utils.escape_html(row.payment_type || "") + "</td>" +
						"<td>" + frappe.utils.escape_html(row.party_name || row.party || "") + "</td>" +
						"<td class='text-end'>" + fmtMoney(amount) + "</td>" +
						"<td>" + frappe.utils.escape_html(row.mode_of_payment || "-") + "</td>" +
						"<td>" + frappe.utils.escape_html(row.reference_no || "-") + "</td>" +
						"<td><span class='indicator-pill " + statusClass + "'>" + frappe.utils.escape_html(row.status || "") + "</span></td>" +
						"<td><a href='/app/payment-entry/" + encodeURIComponent(row.name) + "' class='btn btn-xs btn-default'>" + __("Ouvrir") + "</a></td>" +
						"</tr>";
				});

				html += "</tbody></table>";
			}

			$body.html(html);
		});
	}

	$filters.find(".erp-pay-refresh").on("click", render);

	render();
};
