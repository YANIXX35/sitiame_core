// Copyright (c) 2026, Sitiame Capital
// License: MIT

frappe.query_reports["Journal des ecritures"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Société"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("Du"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("Au"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "account",
			label: __("Compte"),
			fieldtype: "Link",
			options: "Account",
			get_query: function () {
				return { filters: { company: frappe.query_report.get_filter_value("company"), is_group: 0 } };
			},
		},
		{
			fieldname: "voucher_type",
			label: __("Type de pièce"),
			fieldtype: "Select",
			options: ["", "Purchase Invoice", "Sales Invoice", "Payment Entry", "Journal Entry", "Stock Entry", "Purchase Receipt", "Delivery Note"],
		},
	],
};
