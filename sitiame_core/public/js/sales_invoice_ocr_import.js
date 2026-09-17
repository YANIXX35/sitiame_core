// Adds an "Importer une facture" button on the Sales Invoice form.
// v1 scope: scans the uploaded file via OCR.space, shows the raw
// extracted text, and best-effort fills posting_date + adds one line
// item for the detected total amount -- the user reviews/completes the
// rest by hand (client, real item breakdown, etc).
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (!frm.is_new()) return;

		frm.add_custom_button(__("Importer une facture"), function () {
			var uploader = new frappe.ui.FileUploader({
				folder: "Home",
				on_success: function (file_doc) {
					frappe.dom.freeze(__("Lecture du document en cours..."));
					frappe
						.call({
							method: "sitiame_core.api.ocr_extract_invoice",
							args: { file_url: file_doc.file_url },
						})
						.then(function (r) {
							frappe.dom.unfreeze();
							var data = r.message || {};

							if (data.date) {
								frm.set_value("posting_date", data.date);
							}
							if (data.amount) {
								frm.add_child("items", {
									item_name: __("Montant importe (a verifier)"),
									description: __("Ligne ajoutee automatiquement depuis le document importe -- a completer/corriger."),
									qty: 1,
									rate: data.amount,
								});
								frm.refresh_field("items");
							}

							frappe.msgprint({
								title: __("Texte extrait du document"),
								indicator: "blue",
								message:
									"<div style='white-space:pre-wrap;max-height:400px;overflow:auto;font-size:12px;'>" +
									frappe.utils.escape_html(data.text || __("Aucun texte detecte.")) +
									"</div>",
							});
						})
						.catch(function () {
							frappe.dom.unfreeze();
						});
				},
			});
			uploader.show();
		});
	},
});
