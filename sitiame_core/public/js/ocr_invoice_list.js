// OCR import button on the Purchase Invoice / Sales Invoice / Payment Entry
// list views. Loaded through the doctype_list_js hook, i.e. after
// ERPNext's own *_list.js has defined frappe.listview_settings[doctype],
// so this extends its onload instead of being overwritten by it. The
// upload/draft logic lives in sales_invoice_ocr_import.js (app_include_js).
[
	["Purchase Invoice", __("Importer une facture")],
	["Sales Invoice", __("Importer une facture")],
	["Payment Entry", __("Importer un recu")],
].forEach(function (pair) {
	var doctype = pair[0];
	var label = pair[1];
	var settings = (frappe.listview_settings[doctype] = frappe.listview_settings[doctype] || {});
	if (settings.sitiame_ocr_button) return;
	settings.sitiame_ocr_button = true;

	var previous_onload = settings.onload;
	settings.onload = function (listview) {
		if (previous_onload) previous_onload(listview);
		listview.page.add_inner_button(label, function () {
			window.sitiame_create_invoice_draft_from_scan(doctype, frappe.defaults.get_user_default("Company"));
		});
	};
});
