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
	var lineItems = data.line_items || [];
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

	// dynamicTypeField: set on doctypes like Payment Entry where the party
	// isn't a plain Link field but a Dynamic Link (party_type + party) --
	// pass the party_type fieldname and it's set to `doctype` right before
	// linkField, exactly like frm.set_value("party_type", "Supplier") then
	// frm.set_value("party", "ACME") would do by hand.
	function match_and_set_party(linkField, doctype, nameField, extractedName, dynamicTypeField) {
		if (!extractedName || !frm.fields_dict[linkField] || frm.doc[linkField]) return;
		frappe.db
			.get_list(doctype, {
				filters: [[nameField, "like", "%" + extractedName + "%"]],
				fields: ["name"],
				limit: 2,
			})
			.then(function (matches) {
				if (matches && matches.length === 1) {
					if (dynamicTypeField) frm.set_value(dynamicTypeField, doctype);
					frm.set_value(linkField, matches[0].name);
					filled.push(linkField + " ← " + matches[0].name + " (" + __("correspondance sur le nom") + ")");
					// eslint-disable-next-line no-console
					console.log("[OCR] Mapping:", linkField, "->", matches[0].name);
				} else if (!matches || matches.length === 0) {
					// No existing record matches the OCR-extracted name --
					// create one automatically instead of leaving the field
					// blank, so the imported document is immediately
					// usable. Only on a clean zero-match: an ambiguous 2+
					// match is still left for the user to resolve by hand,
					// never auto-picked.
					var newParty = {};
					newParty[nameField] = extractedName;
					frappe.db
						.insert({ doctype: doctype, ...newParty })
						.then(function (created) {
							if (dynamicTypeField) frm.set_value(dynamicTypeField, doctype);
							frm.set_value(linkField, created.name);
							filled.push(
								linkField + " ← " + created.name + " (" + __("nouveau, cree automatiquement") + ")"
							);
							// eslint-disable-next-line no-console
							console.log("[OCR] Created new", doctype, "->", created.name);
						})
						.catch(function (e) {
							// eslint-disable-next-line no-console
							console.log("[OCR] Could not auto-create", doctype, extractedName, e);
						});
				}
			});
	}

	// Journal Entry only: pre-fill the party-side line of the double
	// entry (Supplier -> credit payable, Customer -> debit receivable),
	// then force a blocking confirmation -- see the Journal Entry branch
	// above for why the offsetting line is never guessed.
	function add_journal_party_row(supplierName, customerName, amount) {
		var partyName = supplierName || customerName;
		if (!partyName || !amount || !frm.fields_dict["accounts"]) return;

		var partyType = supplierName ? "Supplier" : "Customer";
		var nameField = partyType === "Supplier" ? "supplier_name" : "customer_name";

		frappe.db
			.get_list(partyType, { filters: [[nameField, "like", "%" + partyName + "%"]], fields: ["name"], limit: 2 })
			.then(function (matches) {
				if (matches && matches.length === 1) return matches[0].name;
				if (!matches || matches.length === 0) {
					var newParty = {};
					newParty[nameField] = partyName;
					return frappe.db.insert({ doctype: partyType, ...newParty }).then(function (created) {
						return created.name;
					});
				}
				return null; // ambiguous 2+ matches: don't guess which one
			})
			.then(function (resolvedName) {
				if (!resolvedName) return;

				var accountFieldname = partyType === "Supplier" ? "default_payable_account" : "default_receivable_account";
				frappe.db.get_value("Company", frm.doc.company, accountFieldname).then(function (r) {
					var defaultAccount = r && r.message ? r.message[accountFieldname] : null;

					var row = frm.add_child("accounts");
					row.party_type = partyType;
					row.party = resolvedName;
					if (defaultAccount) row.account = defaultAccount;
					if (partyType === "Supplier") {
						row.credit_in_account_currency = amount;
					} else {
						row.debit_in_account_currency = amount;
					}
					frm.refresh_field("accounts");
					filled.push("accounts[0] ← " + partyType + " " + resolvedName + " (" + amount + ")");
					// eslint-disable-next-line no-console
					console.log("[OCR] Journal Entry party row:", partyType, resolvedName, amount);

					frappe.msgprint({
						title: __("Ecriture pre-remplie -- a completer avant enregistrement"),
						indicator: "orange",
						message: __(
							"Une ligne a ete pre-remplie automatiquement ({0} : {1}, {2}). Cette seule ligne ne suffit PAS a equilibrer l'ecriture : ajoutez la ligne de contrepartie (compte de charge, banque, etc.) et verifiez le sens debit/credit avant d'enregistrer.",
							[partyType === "Supplier" ? __("Fournisseur") : __("Client"), resolvedName, amount]
						),
					});
				});
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

	// Fills one real row per parsed table line (Designation/Reference/Qte/
	// Unite or similar -- see api.py::_extract_line_items). Only item_name
	// and qty are set: item_code/uom are Link fields that must match an
	// existing Item/UOM master record, which this has no way to verify, so
	// it never guesses those -- the user picks the right item per row.
	function add_line_items(lineItems) {
		if (!lineItems || !lineItems.length) return;
		var itemsField = frm.fields_dict["items"];
		if (!itemsField || itemsField.df.fieldtype !== "Table") return;

		lineItems.forEach(function (entry, idx) {
			var blankRow =
				idx === 0
					? (frm.doc.items || []).find(function (row) {
							return !row.item_name && !row.rate && !row.qty;
					  })
					: null;
			var row = blankRow || frm.add_child("items");
			frappe.model.set_value(row.doctype, row.name, "item_name", entry.item_name);
			frappe.model.set_value(
				row.doctype,
				row.name,
				"description",
				__("Ligne ajoutee automatiquement depuis le document importe -- a completer/corriger (code article a choisir).")
			);
			if (entry.qty) frappe.model.set_value(row.doctype, row.name, "qty", entry.qty);
		});
		frm.refresh_field("items");
		filled.push("items (" + lineItems.length + " ligne(s)) ← " + lineItems.map(function (e) { return e.item_name; }).join(", "));
		// eslint-disable-next-line no-console
		console.log("[OCR] Mapping: line_items ->", lineItems);
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
	} else if (frm.doctype === "Purchase Receipt") {
		// Mapping (verified against the real DocFields, 21/09/2026):
		//   invoice_number -> supplier_delivery_note (Data, editable --
		//                     "Bon de Livraison du Fournisseur")
		//   invoice_date   -> posting_date            (Date, editable)
		//   supplier_name  -> supplier                (Link, resolved by name)
		//   line_items     -> items (real rows: item_name + qty)
		// No monetary total field exists in a useful editable form here
		// (rate/net_total/grand_total are all computed) -- nothing is
		// force-written for those, same reasoning as Purchase Invoice.
		set_direct("supplier_delivery_note", fields.invoice_number);
		set_direct("posting_date", fields.invoice_date);
		match_and_set_party("supplier", "Supplier", "supplier_name", fields.supplier_name);
		add_line_items(lineItems);
	} else if (frm.doctype === "Delivery Note") {
		// Symmetric to Purchase Receipt, but for goods going OUT to a
		// customer -- no "supplier delivery note"-equivalent reference
		// field exists here (the delivery note's own number is the
		// document's naming series, same reasoning as Sales Invoice).
		set_direct("posting_date", fields.invoice_date);
		match_and_set_party("customer", "Customer", "customer_name", fields.customer_name);
		add_line_items(lineItems);
	} else if (frm.doctype === "Payment Entry") {
		// Mapping (verified against the real DocFields, 21/09/2026):
		//   invoice_number -> reference_no    (Data, editable)
		//   invoice_date   -> reference_date  (Date, editable)
		//   grand_total    -> paid_amount OR received_amount, depending on
		//                     payment_type ("Pay" vs "Receive") -- Payment
		//                     Entry has no single "amount" field.
		//   supplier_name/customer_name -> party (Dynamic Link: party_type
		//                     must be set first, there is no plain
		//                     "customer"/"supplier" field on this doctype).
		set_direct("reference_no", fields.invoice_number);
		set_direct("reference_date", fields.invoice_date);

		if (fields.grand_total) {
			var amountField = frm.doc.payment_type === "Receive" ? "received_amount" : "paid_amount";
			set_direct(amountField, fields.grand_total);
		}

		var extractedParty = fields.supplier_name || fields.customer_name;
		var partyType = fields.supplier_name ? "Supplier" : "Customer";
		if (extractedParty && frm.fields_dict["party"] && !frm.doc.party) {
			var nameField = partyType === "Supplier" ? "supplier_name" : "customer_name";
			match_and_set_party("party", partyType, nameField, extractedParty, "party_type");
		}
	} else if (frm.doctype === "Journal Entry") {
		// Mapping (verified against the real DocFields, 22/09/2026):
		// reference number/date and posting date are plain editable
		// fields. The "accounts" table (Journal Entry Account) has
		// account/party_type/party/debit_in_account_currency/
		// credit_in_account_currency -- no item_name/qty/rate.
		//
		// A Journal Entry is a full double-entry: this only pre-fills the
		// PARTY side (payable/receivable, from the matched Supplier/
		// Customer's default account on the Company) -- that's the one
		// side an invoice scan can actually justify. The offsetting line
		// (which expense/income/bank account, and confirming the debit/
		// credit direction) is a real accounting judgement call this
		// can't make safely, so it's left for the user -- enforced with a
		// blocking frappe.msgprint right after filling, not just a code
		// comment, so it can't be missed and nothing gets saved without
		// the user seeing it first.
		set_direct("cheque_no", fields.invoice_number);
		set_direct("cheque_date", fields.invoice_date);
		set_direct("posting_date", fields.invoice_date);
		add_journal_party_row(fields.supplier_name, fields.customer_name, fields.grand_total);
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
