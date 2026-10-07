frappe.pages["erp-admin-dashboard"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Tableau de Bord Admin"),
		single_column: true,
	});

	page.add_action_item(__("Rafraîchir"), function () { render(); });

	var $body = $("<div style='padding:0 15px 40px;margin-top:15px;'></div>").appendTo(page.body);

	function fmt_date(d) {
		return d ? frappe.datetime.str_to_user(frappe.datetime.convert_to_system_tz(d)) : "—";
	}

	function kpi_card(label, value, color) {
		color = color || "blue";
		return (
			"<div style='background:#fff;border-radius:8px;padding:20px 24px;min-width:160px;" +
			"flex:1;box-shadow:0 1px 4px rgba(0,0,0,.08);border-top:4px solid var(--" + color + "-500,#3b82f6);'>" +
			"<div style='font-size:2rem;font-weight:700;color:#1a202c;'>" + value + "</div>" +
			"<div style='font-size:.85rem;color:#64748b;margin-top:4px;'>" + label + "</div>" +
			"</div>"
		);
	}

	function section(title) {
		return "<h5 style='margin:28px 0 10px;font-weight:600;color:#374151;border-bottom:1px solid #e5e7eb;padding-bottom:6px;'>" + title + "</h5>";
	}

	function badge(text, color) {
		return "<span class='indicator-pill " + (color || "gray") + "' style='font-size:.75rem;'>" + text + "</span>";
	}

	function table(headers, rows) {
		if (!rows.length) return "<p class='text-muted'>" + __("Aucune donnée.") + "</p>";
		var h = headers.map(function (hd) { return "<th>" + hd + "</th>"; }).join("");
		var r = rows.map(function (cells) {
			return "<tr>" + cells.map(function (c) { return "<td>" + (c !== null && c !== undefined ? c : "—") + "</td>"; }).join("") + "</tr>";
		}).join("");
		return "<table class='table table-bordered table-sm bg-white'><thead><tr>" + h + "</tr></thead><tbody>" + r + "</tbody></table>";
	}

	function render() {
		$body.html("<p class='text-muted'>" + __("Chargement…") + "</p>");

		frappe.call({ method: "sitiame_core.api.get_admin_dashboard_data" })
			.then(function (r) {
				var d = r.message || {};
				var kpis = d.kpis || {};
				var html = "";

				// ── KPIs ────────────────────────────────────────────────
				html += "<div style='display:flex;gap:16px;flex-wrap:wrap;margin-bottom:8px;'>" +
					kpi_card(__("Utilisateurs inscrits"), kpis.total_users || 0, "blue") +
					kpi_card(__("PME avec société"), kpis.pme_actives || 0, "green") +
					kpi_card(__("Abonnements actifs"), kpis.abonnements_actifs || 0, "yellow") +
					kpi_card(__("Dossiers en attente"), kpis.dossiers_en_attente || 0, "red") +
					"</div>";

				// ── Dernières PME inscrites ──────────────────────────────
				html += section(__("Dernières PME inscrites"));
				html += table(
					[__("Nom"), __("Email"), __("Société"), __("Chargé d'affaires"), __("Inscrit le"), __("Dernière connexion")],
					(d.dernieres_pme || []).map(function (u) {
						return [
							"<strong>" + frappe.utils.escape_html(u.full_name || "—") + "</strong>",
							frappe.utils.escape_html(u.email),
							frappe.utils.escape_html(u.company || "—"),
							frappe.utils.escape_html(u.charge_affaires || "—"),
							fmt_date(u.inscrit_le),
							u.last_active ? fmt_date(u.last_active) : badge(__("Jamais"), "red"),
						];
					})
				);

				// ── Dossiers financement ─────────────────────────────────
				html += section(__("Dossiers de financement par statut"));
				html += table(
					[__("Statut"), __("Nombre")],
					(d.dossiers_financement || []).map(function (s) {
						return [frappe.utils.escape_html(s.status || __("Sans statut")), "<strong>" + s.nb + "</strong>"];
					})
				);

				// ── Scoring ──────────────────────────────────────────────
				html += section(__("Scoring — répartition par tranche"));
				html += table(
					[__("Tranche"), __("Nombre de dossiers")],
					(d.scoring_stats || []).map(function (s) {
						return [frappe.utils.escape_html(s.tranche), "<strong>" + s.nb + "</strong>"];
					})
				);
				if (!(d.scoring_stats || []).length) {
					html += "<p class='text-muted'>" + __("Aucun dossier scoré.") + "</p>";
				}

				// ── Expirations abonnement ───────────────────────────────
				html += section(__("Expirations d'abonnement — 30 prochains jours"));
				if ((d.expirations || []).length) {
					html += table(
						[__("Société"), __("Email"), __("Expire le"), __("Jours restants")],
						d.expirations.map(function (e) {
							var j = parseInt(e.jours_restants, 10);
							var c = j <= 7 ? "red" : j <= 15 ? "orange" : "yellow";
							return [
								frappe.utils.escape_html(e.company),
								frappe.utils.escape_html(e.email || "—"),
								fmt_date(e.expires_on),
								badge(j + " " + __("j"), c),
							];
						})
					);
				} else {
					html += "<p class='text-muted'>" + __("Aucune expiration dans les 30 prochains jours.") + "</p>";
				}

				// ── Chargés d'affaires ───────────────────────────────────
				html += section(__("Chargés d'affaires — portefeuille PME"));
				html += table(
					[__("Chargé d'affaires"), __("Email"), __("Nb PME")],
					(d.portefeuilles || []).map(function (p) {
						return [
							frappe.utils.escape_html(p.full_name || p.charge_affaires),
							frappe.utils.escape_html(p.charge_affaires),
							"<strong>" + p.nb_pme + "</strong>",
						];
					})
				);
				if (!(d.portefeuilles || []).length) {
					html += "<p class='text-muted'>" + __("Aucun chargé d'affaires assigné.") + "</p>";
				}

				// ── Alertes ──────────────────────────────────────────────
				var alertes = d.alertes || {};
				html += section(__("Alertes"));

				var sans_soc = alertes.pme_sans_societe || [];
				html += "<h6 style='font-weight:600;margin:12px 0 6px;'>" +
					badge(sans_soc.length, sans_soc.length ? "red" : "green") +
					" &nbsp;" + __("PME sans société assignée") + "</h6>";
				if (sans_soc.length) {
					html += table(
						[__("Nom"), __("Email"), __("Inscrit le")],
						sans_soc.map(function (u) {
							return [
								frappe.utils.escape_html(u.full_name || "—"),
								frappe.utils.escape_html(u.email),
								fmt_date(u.inscrit_le),
							];
						})
					);
				}

				var jamais = alertes.jamais_connectes || [];
				html += "<h6 style='font-weight:600;margin:16px 0 6px;'>" +
					badge(jamais.length, jamais.length ? "orange" : "green") +
					" &nbsp;" + __("Utilisateurs jamais connectés") + "</h6>";
				if (jamais.length) {
					html += table(
						[__("Nom"), __("Email"), __("Inscrit le")],
						jamais.map(function (u) {
							return [
								frappe.utils.escape_html(u.full_name || "—"),
								frappe.utils.escape_html(u.email),
								fmt_date(u.inscrit_le),
							];
						})
					);
				}

				$body.html(html);
			})
			.catch(function () {
				$body.html("<p class='text-danger'>" + __("Impossible de charger le tableau de bord (voir le journal des erreurs).") + "</p>");
			});
	}

	render();
};
