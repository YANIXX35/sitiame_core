// Copyright (c) 2026, Sitiame Capital
// License: MIT

// ERPNext's standard statements open on the SYSCOHADA liasse layout
// (Financial Report Template, see syscohada_templates.py) for a company on
// a numbered chart. The template stays a normal filter: clearing it gives
// ERPNext's own layout back.
(function () {
	const REPORTS = ["Balance Sheet", "Profit and Loss Statement", "Cash Flow"];

	function preselect(report_name, report) {
		const company = report.get_filter_value("company");
		if (!company || report.get_filter_value("report_template")) return;
		frappe.call({
			method: "sitiame_core.syscohada_templates.default_template",
			args: { report: report_name, company: company },
			callback: function (r) {
				if (r.message && !report.get_filter_value("report_template")) {
					report.set_filter_value("report_template", r.message);
				}
			},
		});
	}

	function wrap(report_name, settings) {
		if (!settings || settings.__sitiame_syscohada) return settings;
		const onload = settings.onload;
		settings.onload = function (report) {
			if (onload) onload.apply(this, arguments);
			preselect(report_name, report);
		};
		settings.__sitiame_syscohada = true;
		return settings;
	}

	frappe.provide("frappe.query_reports");
	frappe.query_reports = new Proxy(frappe.query_reports, {
		set: function (target, name, value) {
			target[name] = REPORTS.includes(name) ? wrap(name, value) : value;
			return true;
		},
	});
	REPORTS.forEach((name) => wrap(name, frappe.query_reports[name]));
})();
