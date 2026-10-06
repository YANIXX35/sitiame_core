// Copyright (c) 2026, Sitiame Capital
// License: MIT

// The chargé d'affaires' home: his portfolio of PMEs, his follow-ups and
// the dossiers left to complete (sitiame_core.portfolio).
frappe.pages["erp-charge-affaires"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Chargé d'affaires"),
		single_column: true,
	});
	page.set_primary_action(__("Inscrire une PME"), function () {
		frappe.set_route("erp-inscrire-pme");
	}, "add");
	page.set_secondary_action(__("Actualiser"), load);

	var esc = frappe.utils.escape_html;
	var $body = $("<div style='padding: 0 15px 30px;'></div>").appendTo(page.body);

	var SUB_COLORS = { Actif: "green", Essai: "orange", "Expiré": "red", Aucun: "gray" };
	var FIN_COLORS = {
		"A examiner": "orange",
		"En cours d'analyse": "blue",
		"Avis favorable": "green",
		"Avis defavorable": "red",
		"Ajourne": "gray",
	};

	function card(title, inner) {
		return (
			"<div style='background: var(--card-bg, #fff); border: 1px solid var(--border-color); border-radius: 12px; padding: 16px 18px; margin-bottom: 18px;'>" +
			"<h5 style='font-weight: 700; margin: 0 0 12px;'>" + title + "</h5>" + inner + "</div>"
		);
	}

	function pill(text, color) {
		return "<span class='indicator-pill " + (color || "gray") + "'>" + esc(text) + "</span>";
	}

	function money(value) {
		return value ? format_currency(value, "XOF") : "-";
	}

	function subState(sub) {
		if (!sub) return "Aucun";
		if (sub.active) return "Actif";
		if (sub.in_trial) return "Essai";
		return sub.ends_on ? "Expiré" : "Aucun";
	}

	function portfolioTable(rows) {
		if (!rows.length) {
			return "<p class='text-muted'>" + __("Aucune PME ne vous est encore attribuée. Un administrateur l'indique dans le champ « Chargé d'affaires » de la fiche Société.") + "</p>";
		}
		var html = "<div style='overflow-x: auto;'><table class='table table-bordered' style='font-size: 13px; margin: 0; min-width: 760px;'><thead><tr>" +
			"<th>" + __("PME") + "</th><th>" + __("Abonnement") + "</th><th>" + __("Scoring") + "</th><th>" + __("Financement") + "</th><th>" + __("Actions") + "</th>" +
			"</tr></thead><tbody>";
		rows.forEach(function (row, i) {
			var s = row.scoring;
			var f = row.financing;
			var scoring = s
				? "<a href='#' class='ca-open' data-doctype='Credit Scoring Dossier' data-name='" + esc(s.name) + "'>" + esc(s.name) + "</a><br>" +
				  __("Note") + " " + (s.score != null ? esc(String(s.score)) : "-") + (s.grade ? " (" + esc(s.grade) + ")" : "") + " · " + esc(s.decision || "") +
				  (s.ready ? "" : " " + pill(__("à compléter"), "orange"))
				: "<span class='text-muted'>" + __("Aucun dossier") + "</span>";
			var financing = f
				? "<a href='#' class='ca-open' data-doctype='Financing Dossier' data-name='" + esc(f.name) + "'>" + esc(f.name) + "</a><br>" +
				  pill(f.status || "-", FIN_COLORS[f.status]) + " " + money(f.amount_requested)
				: "<span class='text-muted'>" + __("Aucun dossier") + "</span>";
			var state = subState(row.subscription);
			html += "<tr>" +
				"<td><b>" + esc(row.company_name) + "</b></td>" +
				"<td>" + pill(__(state), SUB_COLORS[state]) +
				(row.subscription && row.subscription.ends_on ? "<br><span class='text-muted small'>" + __("jusqu'au") + " " + frappe.datetime.str_to_user(row.subscription.ends_on) + "</span>" : "") + "</td>" +
				"<td>" + scoring + "</td>" +
				"<td>" + financing + "</td>" +
				"<td style='white-space: nowrap;'>" +
					"<button class='btn btn-xs btn-default ca-scoring' data-i='" + i + "'>" + (s ? __("Scoring") : __("+ Scoring")) + "</button> " +
					"<button class='btn btn-xs btn-default ca-financing' data-i='" + i + "'>" + (f ? __("Financement") : __("+ Financement")) + "</button><br style='margin-bottom: 4px;'>" +
					"<button class='btn btn-xs btn-default ca-liasse' data-i='" + i + "' style='margin-top: 4px;'>" + __("Liasse") + "</button> " +
					"<button class='btn btn-xs btn-default ca-kyc' style='margin-top: 4px;'>" + __("KYC") + "</button> " +
					"<button class='btn btn-xs btn-primary ca-link' data-i='" + i + "' style='margin-top: 4px;'>" + __("Lien de paiement") + "</button>" +
					"<br><button class='btn btn-xs btn-success ca-compta' data-i='" + i + "' style='margin-top: 4px;'>" + __("Comptabilité") + "</button>" +
				"</td></tr>";
		});
		return html + "</tbody></table></div>";
	}

	function relances(data) {
		var items = [];
		(data.todos || []).forEach(function (t) {
			var text = $("<div>").html(t.description || "").text();
			items.push("<li><a href='#' class='ca-open' data-doctype='ToDo' data-name='" + esc(t.name) + "'>" + esc(text.slice(0, 120) || t.name) + "</a>" +
				(t.date ? " <span class='text-muted small'>(" + frappe.datetime.str_to_user(t.date) + ")</span>" : "") + "</li>");
		});
		(data.opportunities || []).forEach(function (o) {
			items.push("<li>" + __("Opportunité") + " <a href='#' class='ca-open' data-doctype='Opportunity' data-name='" + esc(o.name) + "'>" + esc(o.title || o.customer_name || o.name) + "</a> " +
				pill(__(o.status), "blue") + " " + money(o.opportunity_amount) + "</li>");
		});
		return items.length ? "<ul style='margin: 0; padding-left: 18px;'>" + items.join("") + "</ul>"
			: "<p class='text-muted' style='margin: 0;'>" + __("Aucune relance en cours.") + "</p>";
	}

	function aCompleter(data) {
		var items = [];
		(data.scorings || []).forEach(function (s) {
			items.push("<li>" + __("Scoring") + " <a href='#' class='ca-open' data-doctype='Credit Scoring Dossier' data-name='" + esc(s.name) + "'>" + esc(s.name) + "</a> — " + esc(s.company) + "</li>");
		});
		(data.financings || []).forEach(function (f) {
			items.push("<li>" + __("Financement") + " <a href='#' class='ca-open' data-doctype='Financing Dossier' data-name='" + esc(f.name) + "'>" + esc(f.name) + "</a> — " + esc(f.company) + "</li>");
		});
		return items.length ? "<ul style='margin: 0; padding-left: 18px;'>" + items.join("") + "</ul>"
			: "<p class='text-muted' style='margin: 0;'>" + __("Tous vos dossiers sont complets.") + "</p>";
	}

	function openCompany(company, route) {
		frappe.call({
			method: "sitiame_core.api.set_default_company_for_user",
			args: { company: company },
			freeze: true,
			freeze_message: __("Ouverture de la comptabilité..."),
		}).then(function () {
			frappe.defaults.update_user_default("company", company);
			frappe.set_route(route || "Invoicing");
		}).catch(function () {
			frappe.set_route(route || "Invoicing");
		});
	}

	function historiqueTable(rows) {
		if (!rows || !rows.length) {
			return "<p class='text-muted'>" + __("Aucune inscription enregistrée.") + "</p>";
		}
		var html = "<div style='overflow-x: auto;'><table class='table table-bordered' style='font-size: 13px; margin: 0; min-width: 560px;'><thead><tr>" +
			"<th>" + __("PME") + "</th><th>" + __("Ville") + "</th><th>" + __("Date d'inscription") + "</th><th>" + __("Actions") + "</th>" +
			"</tr></thead><tbody>";
		rows.forEach(function (row) {
			html += "<tr>" +
				"<td><b>" + esc(row.company_name) + "</b><br><span class='text-muted small'>" + esc(row.company) + "</span></td>" +
				"<td>" + esc(row.city || "-") + "</td>" +
				"<td>" + (row.creation ? frappe.datetime.str_to_user(row.creation.substring(0, 10)) : "-") + "</td>" +
				"<td style='white-space: nowrap;'>" +
					"<button class='btn btn-xs btn-success ca-compta-hist' data-company='" + esc(row.company) + "'>" + __("Comptabilité") + "</button> " +
					"<button class='btn btn-xs btn-default ca-open-company' data-company='" + esc(row.company) + "'>" + __("Fiche société") + "</button>" +
				"</td></tr>";
		});
		return html + "</tbody></table></div>";
	}

	// A single-use Jèko link for one of his PMEs: the PME picks its operator
	// when it opens the link (sitiame_core.subscription_api).
	function paymentLink(row) {
		frappe.call({
			method: "sitiame_core.subscription_api.create_company_payment_link",
			args: { company: row.company },
			freeze: true,
			freeze_message: __("Génération du lien Jèko..."),
		}).then(function (r) {
			var link = (r.message || {}).payment_url;
			if (!link) return;
			frappe.utils.copy_to_clipboard(link);
			frappe.msgprint({
				title: __("Lien de paiement — {0}", [row.company_name]),
				message: __("Lien Jèko à usage unique (1 mois), copié dans le presse-papiers : envoyez-le à la PME, elle choisira son opérateur en l'ouvrant.") +
					"<br><br><a href='" + encodeURI(link).replace(/'/g, "%27") + "' target='_blank'>" + esc(link) + "</a>",
			});
		});
	}

	function load() {
		$body.html("<p class='text-muted'>" + __("Chargement...") + "</p>");
		frappe.call({ method: "sitiame_core.portfolio.get_charge_affaires_dashboard" }).then(function (r) {
			var data = r.message || {};
			var rows = data.pme || [];
			var pending = (data.en_inscription || []).length
				? "<div class='alert alert-info' style='margin: 12px 0 0; font-size: 13px;'>" + __("En cours d'inscription (la société est en création) :") + " " +
				  data.en_inscription.map(esc).join(", ") + "</div>"
				: "";
			$body.html(
				card(__("Mon portefeuille") + " <span class='text-muted' style='font-weight: 400;'>(" + rows.length + ")</span>", portfolioTable(rows) + pending) +
				"<div class='row'>" +
					"<div class='col-md-6'>" + card(__("Mes relances"), relances(data.relances || {})) + "</div>" +
					"<div class='col-md-6'>" + card(__("Dossiers à compléter"), aCompleter(data.a_completer || {})) + "</div>" +
				"</div>" +
				card(__("Historique des inscriptions") + " <span class='text-muted' style='font-weight: 400;'>(" + (data.historique || []).length + ")</span>", historiqueTable(data.historique || []))
			);

			$body.find(".ca-open").on("click", function (e) {
				e.preventDefault();
				frappe.set_route("Form", $(this).data("doctype"), $(this).data("name"));
			});
			$body.find(".ca-scoring").on("click", function () {
				var row = rows[$(this).data("i")];
				row.scoring ? frappe.set_route("Form", "Credit Scoring Dossier", row.scoring.name)
					: frappe.new_doc("Credit Scoring Dossier", { company: row.company });
			});
			$body.find(".ca-financing").on("click", function () {
				var row = rows[$(this).data("i")];
				row.financing ? frappe.set_route("Form", "Financing Dossier", row.financing.name)
					: frappe.new_doc("Financing Dossier", { company: row.company });
			});
			$body.find(".ca-liasse").on("click", function () {
				frappe.set_route("query-report", "Liasse SYSCOHADA", { company: rows[$(this).data("i")].company });
			});
			$body.find(".ca-kyc").on("click", function () {
				frappe.set_route("erp-kyc");
			});
			$body.find(".ca-link").on("click", function () {
				paymentLink(rows[$(this).data("i")]);
			});
			$body.find(".ca-compta").on("click", function () {
				openCompany(rows[$(this).data("i")].company, "Invoicing");
			});
			$body.find(".ca-compta-hist").on("click", function () {
				openCompany($(this).data("company"), "Invoicing");
			});
			$body.find(".ca-open-company").on("click", function () {
				frappe.set_route("Form", "Company", $(this).data("company"));
			});
		});
	}

	load();
};
