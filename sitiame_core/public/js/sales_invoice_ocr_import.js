// Adds an "Importer une facture" button on every "new document" form,
// across all doctypes/modules (Sales Invoice, Purchase Invoice, Payment
// Entry, Journal Entry, etc).
// v1 scope: scans the uploaded file via OCR.space, shows the raw
// extracted text, and best-effort fills posting_date/date + adds one
// "items" line for the detected total amount when the doctype has that
// field -- the user reviews/completes the rest by hand.
frappe.ui.form.on("*", {
	refresh(frm) {
		if (!frm.is_new()) return;
		if (frm.custom_buttons && frm.custom_buttons[__("Importer une facture")]) return;

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

							// Only touch fields that actually exist on this doctype.
							var dateField = ["posting_date", "date", "transaction_date"].find(function (f) {
								return frm.fields_dict[f];
							});
							if (data.date && dateField) {
								frm.set_value(dateField, data.date);
							}

							var itemsField = ["items", "accounts"].find(function (f) {
								return frm.fields_dict[f] && frm.fields_dict[f].df.fieldtype === "Table";
							});
							if (data.amount && itemsField === "items") {
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
