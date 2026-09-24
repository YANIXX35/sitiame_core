// "Importer une facture" on the Purchase Invoice / Sales Invoice list views.
// Loaded through the doctype_list_js hook, i.e. after ERPNext's own
// *_list.js has defined frappe.listview_settings[doctype], so this extends
// its onload instead of being overwritten by it. The upload/draft logic
// lives in sales_invoice_ocr_import.js (app_include_js).
["Purchase Invoice", "Sales Invoice"].forEach(function (doctype) {
	var settings = (frappe.listview_settings[doctype] = frappe.listview_settings[doctype] || {});
	if (settings.sitiame_ocr_button) return;
	settings.sitiame_ocr_button = true;

	var previous_onload = settings.onload;
	settings.onload = function (listview) {
		if (previous_onload) previous_onload(listview);
		listview.page.add_inner_button(__("Importer une facture"), function () {
			window.sitiame_create_invoice_draft_from_scan(doctype, frappe.defaults.get_user_default("Company"));
		});
	};
});
