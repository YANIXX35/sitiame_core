// "Telecharger" button on the list views below: the checked rows, else
// every row matching the list's current filters, as PDF, Word, Excel or
// CSV (sitiame_core/exports.py). Loaded through doctype_list_js, i.e.
// after ERPNext's own *_list.js, so it extends onload instead of being
// overwritten by it (same pattern as ocr_invoice_list.js).
[
	"Sales Invoice",
	"Purchase Invoice",
	"Payment Entry",
	"Journal Entry",
	"Stock Entry",
	"Purchase Receipt",
	"Delivery Note",
	"Purchase Order",
	"Sales Order",
	"Item",
].forEach(function (doctype) {
	var settings = (frappe.listview_settings[doctype] = frappe.listview_settings[doctype] || {});
	if (settings.sitiame_download_button) return;
	settings.sitiame_download_button = true;

	var previous_onload = settings.onload;
	settings.onload = function (listview) {
		if (previous_onload) previous_onload(listview);
		listview.page.add_inner_button(__("Telecharger"), function () {
			window.sitiame_open_download_dialog(listview);
		});
	};
});

window.sitiame_open_download_dialog = function (listview) {
	var checked = listview.get_checked_items(true);
	var scope = { doctype: listview.doctype };
	if (checked.length) {
		scope.names = checked;
	} else {
		scope.filters = listview.get_filters_for_args();
	}

	var dialog = new frappe.ui.Dialog({
		title: __("Telecharger"),
		fields: [
			{
				fieldname: "fmt",
				fieldtype: "Select",
				label: __("Format"),
				reqd: 1,
				default: "pdf",
				options: [
					{ value: "pdf", label: "PDF" },
					{ value: "docx", label: "Word (.docx)" },
					{ value: "xlsx", label: "Excel (.xlsx)" },
					{ value: "csv", label: "CSV" },
				],
				onchange: function () {
					refresh_count();
				},
			},
			{ fieldname: "info", fieldtype: "HTML" },
		],
		primary_action_label: __("Telecharger"),
		primary_action: function (values) {
			var c = dialog.sitiame_count;
			if (!c || !c.count || c.count > c.limit) return;
			open_url_post("/api/method/sitiame_core.exports.download", Object.assign({ fmt: values.fmt }, scope));
			dialog.hide();
		},
	});

	function refresh_count() {
		var fmt = dialog.get_value("fmt");
		dialog.sitiame_count = null;
		dialog.fields_dict.info.$wrapper.html("<p class='text-muted'>" + __("Comptage en cours...") + "</p>");
		frappe.call({
			method: "sitiame_core.exports.count_documents",
			args: Object.assign({ fmt: fmt }, scope),
		}).then(function (r) {
			if (dialog.get_value("fmt") !== fmt) return;
			var c = r.message || {};
			dialog.sitiame_count = c;
			var html;
			if (!c.count) {
				html = "<p class='text-muted'>" + __("Aucun document a telecharger.") + "</p>";
			} else if (c.count > c.limit) {
				html =
					"<p class='text-danger'>" +
					__("Plus de {0} documents : filtrez davantage (par mois par exemple) pour ce format.", [c.limit]) +
					"</p>";
			} else {
				html =
					"<p>" +
					(checked.length
						? __("{0} document(s) coche(s)", [c.count])
						: __("{0} document(s) selon les filtres de la liste", [c.count])) +
					"</p>";
			}
			if (c.note) {
				// e.g. cancelled documents, which ERPNext refuses to print
				html += "<p class='text-muted small'>" + frappe.utils.escape_html(c.note) + "</p>";
			}
			dialog.fields_dict.info.$wrapper.html(html);
		});
	}

	dialog.show();
	refresh_count();
};
