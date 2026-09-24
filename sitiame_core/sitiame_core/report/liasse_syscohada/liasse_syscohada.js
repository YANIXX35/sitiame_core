// Copyright (c) 2026, Sitiame Capital
// License: MIT

frappe.query_reports["Liasse SYSCOHADA"] = {
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
			fieldname: "fiscal_year",
			label: __("Exercice"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			reqd: 1,
		},
		{
			fieldname: "statement",
			label: __("État"),
			fieldtype: "Select",
			options: ["Bilan actif", "Bilan passif", "Compte de résultat"],
			default: "Bilan actif",
			reqd: 1,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.bold) {
			value = "<b>" + value + "</b>";
		}
		return value;
	},
};
