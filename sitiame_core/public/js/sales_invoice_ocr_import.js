// Adds an "Importer une facture" button on every "new document" form,
// across all doctypes/modules (Sales Invoice, Purchase Invoice, Payment
// Entry, Journal Entry, etc).
//
// v2: the server (sitiame_core.api.ocr_extract_invoice) now returns a
// structured `fields` object (invoice_number, invoice_date, due_date,
// supplier_name, customer_name, tax_id, subtotal, tax_amount, grand_total)
// on top of the raw text, built by label-matching the OCR text -- see
// api.py::_extract_invoice_fields. A field is only present when it was
// actually found on the document: nothing here invents or defaults a
// value that wasn't printed on the paper.
//
// Purchase Invoice/Sales Invoice get a real field-by-field mapping (see
// below for exactly which fields are editable vs server-computed).
// Every other doctype keeps the old generic best-effort behaviour
// (date + fuzzy party match) unchanged, so nothing that worked before
// is broken by this.
//
// Nothing is auto-saved: the form is filled, the user reviews/edits,
// then saves manually like any other document.
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
							handle_ocr_result(frm, r.message || {});
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

function handle_ocr_result(frm, data) {
	var fields = data.fields || {};
	var confidence = data.confidence || {};
	var filled = [];

	// eslint-disable-next-line no-console
	console.log("[OCR] Document type:", data.document_type);
	// eslint-disable-next-line no-console
	console.log("[OCR] Extracted fields:", fields);
	// eslint-disable-next-line no-console
	console.log("[OCR] Confidence:", confidence);

	function set_direct(fieldname, value) {
		if (value === undefined || value === null || value === "") return;
		if (!frm.fields_dict[fieldname]) return;
		frm.set_value(fieldname, value);
		filled.push(fieldname + " ← " + value);
	}

	function match_and_set_party(linkField, doctype, nameField, extractedName) {
		if (!extractedName || !frm.fields_dict[linkField] || frm.doc[linkField]) return;
		frappe.db
			.get_list(doctype, {
				filters: [[nameField, "like", "%" + extractedName + "%"]],
				fields: ["name"],
				limit: 2,
			})
			.then(function (matches) {
				if (matches && matches.length === 1) {
					frm.set_value(linkField, matches[0].name);
					filled.push(linkField + " ← " + matches[0].name + " (" + __("correspondance sur le nom") + ")");
					// eslint-disable-next-line no-console
					console.log("[OCR] Mapping:", linkField, "->", matches[0].name);
				}
			});
	}

	function add_amount_item_row(rateValue, label) {
		if (!rateValue) return;
		var itemsField = frm.fields_dict["items"];
		if (!itemsField || itemsField.df.fieldtype !== "Table") return;
		var blankRow = (frm.doc.items || []).find(function (row) {
			return !row.item_name && !row.rate && !row.qty;
		});
		var row = blankRow || frm.add_child("items");
		frappe.model.set_value(row.doctype, row.name, "item_name", label);
		frappe.model.set_value(
			row.doctype,
			row.name,
			"description",
			__("Ligne ajoutee automatiquement depuis le document importe -- a completer/corriger.")
		);
		frappe.model.set_value(row.doctype, row.name, "qty", 1);
		frappe.model.set_value(row.doctype, row.name, "rate", rateValue);
		frm.refresh_field("items");
		filled.push("items[0].rate ← " + rateValue);
	}

	if (data.document_type && data.document_type !== "invoice") {
		// Not recognised as an invoice (e.g. devis/avoir/bon de commande):
		// don't guess-fill invoice-shaped fields onto an unrelated document.
		frappe.msgprint({
			title: __("Document non reconnu comme facture"),
			indicator: "orange",
			message: __(
				"Le document importe n'a pas ete reconnu comme une facture (type detecte : {0}). Aucun champ n'a ete rempli automatiquement.",
				[data.document_type]
			),
		});
		return;
	}

	if (frm.doctype === "Purchase Invoice") {
		// Mapping (verified against the real DocFields, 21/09/2026):
		//   invoice_number -> bill_no      (Data, editable)
		//   invoice_date   -> bill_date    (Date, editable)
		//   due_date       -> due_date     (Date, editable)
		//   supplier_name  -> supplier     (Link, editable, resolved by name)
		//   tax_id         -> NOT SET: tax_id is read-only, auto-pulled from
		//                     the Supplier master once `supplier` is set.
		//   subtotal/tax_amount/grand_total -> NOT SET directly: net_total,
		//                     total_taxes_and_charges and grand_total are
		//                     server-computed from the items+taxes table,
		//                     read-only on the form. `subtotal` (HT) is used
		//                     to pre-fill one item row instead, so ERPNext's
		//                     own tax engine computes the real totals; the
		//                     OCR's own tax_amount/grand_total are shown in
		//                     the review message for the user to compare
		//                     against, never written to the form directly.
		set_direct("bill_no", fields.invoice_number);
		set_direct("bill_date", fields.invoice_date);
		set_direct("due_date", fields.due_date);
		match_and_set_party("supplier", "Supplier", "supplier_name", fields.supplier_name);
		add_amount_item_row(
			fields.subtotal,
			fields.invoice_number ? __("Facture {0}", [fields.invoice_number]) : __("Montant importe (a verifier)")
		);
	} else if (frm.doctype === "Sales Invoice") {
		// Sales Invoice numbering is auto-generated by naming series -- there
		// is no user-editable "supplier invoice number" field to fill here.
		set_direct("due_date", fields.due_date);
		match_and_set_party("customer", "Customer", "customer_name", fields.customer_name);
		add_amount_item_row(fields.subtotal, __("Montant importe (a verifier)"));
	} else {
		// Any other doctype (Payment Entry, Journal Entry, ...): keep the
		// original generic best-effort behaviour, unchanged.
		var dateField = ["posting_date", "date", "transaction_date"].find(function (f) {
			return frm.fields_dict[f];
		});
		if (data.date && dateField) set_direct(dateField, data.date);

		var partyField = ["customer", "supplier"].find(function (f) {
			return frm.fields_dict[f] && !frm.doc[f];
		});
		if (data.client_name && partyField) {
			var partyDoctype = partyField === "customer" ? "Customer" : "Supplier";
			var nameField = partyField === "customer" ? "customer_name" : "supplier_name";
			match_and_set_party(partyField, partyDoctype, nameField, data.client_name);
		}

		if (data.amount) add_amount_item_row(data.amount, __("Montant importe (a verifier)"));
	}

	// eslint-disable-next-line no-console
	console.log("[OCR] Champs injectes:", filled);

	var summaryOrder = [
		"invoice_number",
		"invoice_date",
		"due_date",
		"supplier_name",
		"customer_name",
		"tax_id",
		"subtotal",
		"tax_amount",
		"grand_total",
	];
	var summaryLabels = {
		invoice_number: __("Numero facture"),
		invoice_date: __("Date facture"),
		due_date: __("Echeance"),
		supplier_name: __("Fournisseur"),
		customer_name: __("Client"),
		tax_id: __("NIF"),
		subtotal: __("Montant HT"),
		tax_amount: __("TVA"),
		grand_total: __("Total TTC"),
	};
	var summaryLines = summaryOrder
		.filter(function (key) {
			return fields[key] !== undefined;
		})
		.map(function (key) {
			var conf = confidence[key];
			var confSuffix = conf
				? " <span style='color:#94a3b8;font-size:11px;'>(" + __("confiance") + " " + Math.round(conf * 100) + "%)</span>"
				: "";
			return "<b>" + summaryLabels[key] + "</b> : " + fields[key] + confSuffix;
		});

	frappe.msgprint({
		title: __("Donnees extraites du document"),
		indicator: summaryLines.length ? "blue" : "orange",
		message:
			(summaryLines.length
				? "<div style='margin-bottom:10px;line-height:1.6;'>" + summaryLines.join("<br>") + "</div>"
				: "<div style='margin-bottom:10px;color:#b45309;'>" +
				  __("Aucune information structuree n'a ete detectee sur ce document -- verifiez et completez manuellement.") +
				  "</div>") +
			"<div style='font-size:11px;color:#64748b;margin-bottom:4px;'>" + __("Texte brut extrait :") + "</div>" +
			"<div style='white-space:pre-wrap;max-height:300px;overflow:auto;font-size:12px;border:1px solid #e2e8f0;padding:8px;border-radius:6px;'>" +
			frappe.utils.escape_html(data.text || __("Aucun texte detecte.")) +
			"</div>",
	});
}
