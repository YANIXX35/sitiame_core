// Copyright (c) 2026, Sitiame Capital
// License: MIT

// A PME account's new stock documents start on its own warehouse
// (frappe.boot.sitiame_warehouse, see account_warehouse.py).
(function () {
	const HEADER = {
		"Sales Invoice": "set_warehouse",
		"POS Invoice": "set_warehouse",
		"Delivery Note": "set_warehouse",
		"Sales Order": "set_warehouse",
		"Purchase Invoice": "set_warehouse",
		"Purchase Receipt": "set_warehouse",
		"Purchase Order": "set_warehouse",
		"Material Request": "set_warehouse",
		"Stock Reconciliation": "set_warehouse",
	};

	Object.keys(HEADER).forEach((doctype) => {
		frappe.ui.form.on(doctype, {
			onload(frm) {
				const warehouse = frappe.boot.sitiame_warehouse;
				const field = HEADER[doctype];
				if (warehouse && frm.is_new() && frm.fields_dict[field] && !frm.doc[field]) {
					frm.set_value(field, warehouse);
				}
			},
		});
	});
})();
