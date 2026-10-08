frappe.pages["erp-admin-dashboard"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Tableau de Bord Admin"),
		single_column: true,
	});

	page.add_action_item(__("Rafraîchir"), function () { render(); });

	// ── Styles ─────────────────────────────────────────────────────────────
	var style = document.createElement("style");
	style.textContent = `
		.sad-wrap {
			padding: 20px 20px 60px;
			font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
		}
		/* KPI row */
		.sad-kpi-row { display:flex; gap:16px; flex-wrap:wrap; margin-bottom:24px; }
		.sad-kpi {
			flex:1; min-width:170px;
			background:#fff; border-radius:14px;
			padding:22px 20px; box-shadow:0 1px 6px rgba(0,0,0,.07);
			position:relative; overflow:hidden;
		}
		.sad-kpi.primary {
			background:linear-gradient(135deg,#15803d,#166534);
			color:#fff;
		}
		.sad-kpi-val {
			font-size:2.2rem; font-weight:700; line-height:1;
			color:#111827;
		}
		.sad-kpi.primary .sad-kpi-val { color:#fff; }
		.sad-kpi-label {
			font-size:.8rem; color:#64748b; margin-top:6px; font-weight:500;
		}
		.sad-kpi.primary .sad-kpi-label { color:rgba(255,255,255,.8); }
		.sad-kpi-arrow {
			position:absolute; top:14px; right:14px;
			width:28px; height:28px; border-radius:8px;
			background:rgba(0,0,0,.06);
			display:flex; align-items:center; justify-content:center;
			cursor:pointer;
		}
		.sad-kpi.primary .sad-kpi-arrow { background:rgba(255,255,255,.2); }
		.sad-kpi-sub {
			font-size:.72rem; margin-top:8px; color:#22c55e; font-weight:600;
		}
		.sad-kpi.primary .sad-kpi-sub { color:rgba(255,255,255,.75); }
		/* Grid body */
		.sad-grid { display:grid; grid-template-columns:1fr 360px; gap:20px; }
		@media(max-width:900px){ .sad-grid { grid-template-columns:1fr; } }
		/* Cards */
		.sad-card {
			background:#fff; border-radius:14px;
			padding:20px 22px; box-shadow:0 1px 6px rgba(0,0,0,.07);
			margin-bottom:20px;
		}
		.sad-card-title {
			font-size:.95rem; font-weight:700; color:#111827;
			margin:0 0 16px; display:flex; align-items:center; justify-content:space-between;
		}
		.sad-card-title span.badge-count {
			background:#f0fdf4; color:#15803d;
			font-size:.72rem; font-weight:700;
			padding:2px 8px; border-radius:99px; border:1px solid #bbf7d0;
		}
		/* PME list */
		.sad-pme-item {
			display:flex; align-items:center; gap:12px;
			padding:10px 0; border-bottom:1px solid #f1f5f9;
		}
		.sad-pme-item:last-child { border-bottom:none; }
		.sad-avatar {
			width:36px; height:36px; border-radius:50%;
			background:linear-gradient(135deg,#15803d,#166534);
			color:#fff; font-size:.85rem; font-weight:700;
			display:flex; align-items:center; justify-content:center;
			flex:none;
		}
		.sad-pme-info { flex:1; min-width:0; }
		.sad-pme-name { font-size:.88rem; font-weight:600; color:#111827; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
		.sad-pme-sub { font-size:.75rem; color:#94a3b8; margin-top:1px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
		.sad-pill {
			font-size:.7rem; font-weight:600; padding:3px 10px; border-radius:99px;
			white-space:nowrap; flex:none;
		}
		.sad-pill-green { background:#f0fdf4; color:#15803d; border:1px solid #bbf7d0; }
		.sad-pill-orange { background:#fff7ed; color:#c2410c; border:1px solid #fed7aa; }
		.sad-pill-red { background:#fef2f2; color:#b91c1c; border:1px solid #fecaca; }
		.sad-pill-blue { background:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe; }
		.sad-pill-gray { background:#f8fafc; color:#64748b; border:1px solid #e2e8f0; }
		/* Dossier list */
		.sad-dos-item {
			display:flex; align-items:center; justify-content:space-between;
			padding:9px 0; border-bottom:1px solid #f1f5f9;
		}
		.sad-dos-item:last-child { border-bottom:none; }
		.sad-dos-name { font-size:.85rem; font-weight:600; color:#111827; }
		.sad-dos-date { font-size:.73rem; color:#94a3b8; margin-top:1px; }
		/* Progress ring */
		.sad-ring-wrap {
			display:flex; align-items:center; gap:20px; flex-wrap:wrap;
		}
		.sad-ring { position:relative; width:90px; height:90px; flex:none; }
		.sad-ring svg { transform:rotate(-90deg); }
		.sad-ring-label {
			position:absolute; inset:0;
			display:flex; align-items:center; justify-content:center;
			font-size:.85rem; font-weight:700; color:#111827;
		}
		/* Bar chart */
		.sad-bar-row {
			display:flex; align-items:center; gap:10px; margin-bottom:10px;
		}
		.sad-bar-lbl { font-size:.78rem; color:#64748b; width:110px; flex:none; text-align:right; }
		.sad-bar-track {
			flex:1; height:10px; background:#f1f5f9; border-radius:99px; overflow:hidden;
		}
		.sad-bar-fill {
			height:100%; border-radius:99px;
			background:linear-gradient(90deg,#15803d,#22c55e);
			transition:width .6s ease;
		}
		.sad-bar-val { font-size:.78rem; font-weight:700; color:#111827; width:30px; text-align:right; }
		/* Alerte cards */
		.sad-alert-card {
			display:flex; gap:12px; align-items:flex-start;
			background:#fff7ed; border:1px solid #fed7aa; border-radius:10px;
			padding:12px 14px; margin-bottom:10px;
		}
		.sad-alert-card.red { background:#fef2f2; border-color:#fecaca; }
		.sad-alert-icon { font-size:1.2rem; flex:none; }
		.sad-alert-title { font-size:.85rem; font-weight:700; color:#111827; }
		.sad-alert-sub { font-size:.75rem; color:#64748b; margin-top:2px; }
		/* Expiration card */
		.sad-exp-item {
			display:flex; align-items:center; justify-content:space-between;
			padding:9px 0; border-bottom:1px solid #f1f5f9;
		}
		.sad-exp-item:last-child { border-bottom:none; }
		.sad-exp-co { font-size:.85rem; font-weight:600; color:#111827; }
		.sad-exp-date { font-size:.73rem; color:#94a3b8; }
		/* Scoring */
		.sad-score-item {
			display:flex; align-items:center; gap:10px; margin-bottom:8px;
		}
		.sad-score-label { font-size:.8rem; color:#374151; font-weight:600; width:80px; flex:none; }
		/* Empty */
		.sad-empty { font-size:.83rem; color:#94a3b8; padding:10px 0; }
		/* Section header link */
		.sad-link-btn {
			font-size:.75rem; color:#15803d; font-weight:600; text-decoration:none;
			padding:3px 10px; border-radius:99px;
			border:1px solid #bbf7d0; background:#f0fdf4;
		}
	`;
	document.head.appendChild(style);

	var $body = $("<div class='sad-wrap'></div>").appendTo(page.body);

	// ── Helpers ─────────────────────────────────────────────────────────────
	function fmt_date(d) {
		return d ? frappe.datetime.str_to_user(frappe.datetime.convert_to_system_tz(d)) : "—";
	}
	function initials(name) {
		if (!name) return "?";
		return name.split(" ").slice(0, 2).map(function (w) { return w[0] || ""; }).join("").toUpperCase();
	}
	function esc(s) { return frappe.utils.escape_html(s || ""); }

	function pill(text, cls) {
		return "<span class='sad-pill " + (cls || "sad-pill-gray") + "'>" + esc(text) + "</span>";
	}

	function ring(pct, label) {
		var r = 38, c = 2 * Math.PI * r;
		var dash = (pct / 100) * c;
		return (
			"<div class='sad-ring'>" +
			"<svg width='90' height='90' viewBox='0 0 90 90'>" +
			"<circle cx='45' cy='45' r='" + r + "' fill='none' stroke='#f1f5f9' stroke-width='9'/>" +
			"<circle cx='45' cy='45' r='" + r + "' fill='none' stroke='#15803d' stroke-width='9'" +
			" stroke-dasharray='" + dash.toFixed(1) + " " + c.toFixed(1) + "' stroke-linecap='round'/>" +
			"</svg>" +
			"<div class='sad-ring-label'>" + pct + "%</div>" +
			"</div>"
		);
	}

	function bar_chart(items, key_label, key_val) {
		if (!items || !items.length) return "<p class='sad-empty'>" + __("Aucune donnée.") + "</p>";
		var max = Math.max.apply(null, items.map(function (i) { return i[key_val] || 0; })) || 1;
		return items.map(function (item) {
			var pct = Math.round((item[key_val] / max) * 100);
			return (
				"<div class='sad-bar-row'>" +
				"<div class='sad-bar-lbl'>" + esc(item[key_label]) + "</div>" +
				"<div class='sad-bar-track'><div class='sad-bar-fill' style='width:" + pct + "%'></div></div>" +
				"<div class='sad-bar-val'>" + item[key_val] + "</div>" +
				"</div>"
			);
		}).join("");
	}

	// ── Render ───────────────────────────────────────────────────────────────
	function render() {
		$body.html("<p class='text-muted' style='padding:40px 0 0 10px;'>" + __("Chargement…") + "</p>");

		frappe.call({ method: "sitiame_core.api.get_admin_dashboard_data" })
			.then(function (r) {
				var d = r.message || {};
				var kpis = d.kpis || {};
				var dernieres = d.dernieres_pme || [];
				var dossiers = d.dossiers_financement || [];
				var scoring = d.scoring_stats || [];
				var expirations = d.expirations || [];
				var portefeuilles = d.portefeuilles || [];
				var alertes = d.alertes || {};
				var sans_soc = alertes.pme_sans_societe || [];
				var jamais = alertes.jamais_connectes || [];

				// ── KPIs ─────────────────────────────────────────────────────
				var kpi_html =
					"<div class='sad-kpi-row'>" +
					/* PRIMARY – PME actives */
					"<div class='sad-kpi primary'>" +
					"<div class='sad-kpi-arrow'>↗</div>" +
					"<div class='sad-kpi-val'>" + (kpis.pme_actives || 0) + "</div>" +
					"<div class='sad-kpi-label'>" + __("PME enregistrées") + "</div>" +
					"<div class='sad-kpi-sub'>↑ " + __("Sociétés actives") + "</div>" +
					"</div>" +
					/* Abonnements */
					"<div class='sad-kpi'>" +
					"<div class='sad-kpi-arrow' style='background:#f0fdf4;color:#15803d;'>↗</div>" +
					"<div class='sad-kpi-val'>" + (kpis.abonnements_actifs || 0) + "</div>" +
					"<div class='sad-kpi-label'>" + __("Abonnements actifs") + "</div>" +
					"<div class='sad-kpi-sub' style='color:#15803d;'>✓ " + __("En cours") + "</div>" +
					"</div>" +
					/* Dossiers en attente */
					"<div class='sad-kpi'>" +
					"<div class='sad-kpi-arrow' style='background:#fff7ed;color:#c2410c;'>!</div>" +
					"<div class='sad-kpi-val'>" + (kpis.dossiers_en_attente || 0) + "</div>" +
					"<div class='sad-kpi-label'>" + __("Dossiers en attente") + "</div>" +
					"<div class='sad-kpi-sub' style='color:#c2410c;'>⚠ " + __("À examiner") + "</div>" +
					"</div>" +
					/* Utilisateurs */
					"<div class='sad-kpi'>" +
					"<div class='sad-kpi-arrow' style='background:#eff6ff;color:#1d4ed8;'>↗</div>" +
					"<div class='sad-kpi-val'>" + (kpis.total_users || 0) + "</div>" +
					"<div class='sad-kpi-label'>" + __("Utilisateurs inscrits") + "</div>" +
					"<div class='sad-kpi-sub' style='color:#1d4ed8;'>● " + __("Comptes actifs") + "</div>" +
					"</div>" +
					"</div>";

				// ── LEFT COL ─────────────────────────────────────────────────
				// Dernières PME inscrites
				var pme_rows = dernieres.map(function (u) {
					var co = u.company || "—";
					var ca = u.charge_affaires ? pill(u.charge_affaires, "sad-pill-blue") : pill(__("Non assigné"), "sad-pill-gray");
					var statut = u.last_active
						? pill(__("Actif"), "sad-pill-green")
						: pill(__("Jamais connecté"), "sad-pill-orange");
					return (
						"<div class='sad-pme-item'>" +
						"<div class='sad-avatar'>" + initials(u.full_name) + "</div>" +
						"<div class='sad-pme-info'>" +
						"<div class='sad-pme-name'>" + esc(u.full_name || "—") + "</div>" +
						"<div class='sad-pme-sub'>" + esc(co) + " · " + esc(u.email) + "</div>" +
						"</div>" +
						ca + "&nbsp;" + statut +
						"</div>"
					);
				}).join("") || "<p class='sad-empty'>" + __("Aucune PME inscrite.") + "</p>";

				var left_col =
					"<div class='sad-card'>" +
					"<div class='sad-card-title'>" + __("Dernières PME inscrites") +
					"<span class='badge-count'>" + dernieres.length + "</span></div>" +
					pme_rows +
					"</div>";

				// Dossiers financement – bar chart
				var df_items = dossiers.map(function (s) { return { tranche: s.status || __("Sans statut"), nb: s.nb }; });
				left_col +=
					"<div class='sad-card'>" +
					"<div class='sad-card-title'>" + __("Dossiers de financement") + "</div>" +
					bar_chart(df_items, "tranche", "nb") +
					"</div>";

				// Scoring – bar chart
				left_col +=
					"<div class='sad-card'>" +
					"<div class='sad-card-title'>" + __("Scoring — répartition par tranche") + "</div>" +
					(scoring.length
						? bar_chart(scoring, "tranche", "nb")
						: "<p class='sad-empty'>" + __("Aucun dossier scoré.") + "</p>") +
					"</div>";

				// ── RIGHT COL ────────────────────────────────────────────────
				// Portefeuille + Progress rings
				var total_pme_ca = portefeuilles.reduce(function (s, p) { return s + (p.nb_pme || 0); }, 0);
				var rings_html = portefeuilles.length
					? "<div class='sad-ring-wrap'>" +
					portefeuilles.map(function (p) {
						var pct = total_pme_ca > 0 ? Math.round((p.nb_pme / total_pme_ca) * 100) : 0;
						return (
							"<div style='text-align:center;'>" +
							ring(pct) +
							"<div style='font-size:.72rem;font-weight:600;color:#374151;margin-top:4px;max-width:80px;'>" +
							esc(p.full_name || p.charge_affaires) + "</div>" +
							"<div style='font-size:.7rem;color:#94a3b8;'>" + p.nb_pme + " PME</div>" +
							"</div>"
						);
					}).join("") +
					"</div>"
					: "<p class='sad-empty'>" + __("Aucun chargé d'affaires.") + "</p>";

				var right_col =
					"<div class='sad-card'>" +
					"<div class='sad-card-title'>" + __("Chargés d'affaires") + "</div>" +
					rings_html +
					"</div>";

				// Expirations
				var exp_rows = expirations.length
					? expirations.map(function (e) {
						var j = parseInt(e.jours_restants, 10);
						var cls = j <= 7 ? "sad-pill-red" : j <= 15 ? "sad-pill-orange" : "sad-pill-gray";
						return (
							"<div class='sad-exp-item'>" +
							"<div>" +
							"<div class='sad-exp-co'>" + esc(e.company) + "</div>" +
							"<div class='sad-exp-date'>" + esc(e.email || "—") + " · " + fmt_date(e.expires_on) + "</div>" +
							"</div>" +
							pill(j + " j", cls) +
							"</div>"
						);
					}).join("")
					: "<p class='sad-empty'>" + __("Aucune expiration dans les 30 prochains jours.") + "</p>";

				right_col +=
					"<div class='sad-card'>" +
					"<div class='sad-card-title'>" + __("Expirations — 30 prochains jours") +
					(expirations.length ? "<span class='badge-count'>" + expirations.length + "</span>" : "") +
					"</div>" +
					exp_rows +
					"</div>";

				// Alertes
				var alert_html = "";
				if (sans_soc.length) {
					alert_html +=
						"<div class='sad-alert-card red'>" +
						"<div class='sad-alert-icon'>⚠</div>" +
						"<div><div class='sad-alert-title'>" + sans_soc.length + " " + __("PME sans société assignée") + "</div>" +
						"<div class='sad-alert-sub'>" + sans_soc.slice(0, 3).map(function (u) { return esc(u.full_name || u.email); }).join(", ") + (sans_soc.length > 3 ? "…" : "") + "</div></div>" +
						"</div>";
				}
				if (jamais.length) {
					alert_html +=
						"<div class='sad-alert-card'>" +
						"<div class='sad-alert-icon'>👤</div>" +
						"<div><div class='sad-alert-title'>" + jamais.length + " " + __("utilisateurs jamais connectés") + "</div>" +
						"<div class='sad-alert-sub'>" + jamais.slice(0, 3).map(function (u) { return esc(u.full_name || u.email); }).join(", ") + (jamais.length > 3 ? "…" : "") + "</div></div>" +
						"</div>";
				}
				if (!alert_html) {
					alert_html = "<p class='sad-empty'>✅ " + __("Aucune alerte en cours.") + "</p>";
				}

				right_col +=
					"<div class='sad-card'>" +
					"<div class='sad-card-title'>" + __("Alertes") + "</div>" +
					alert_html +
					"</div>";

				// ── Assemblage ────────────────────────────────────────────────
				var html =
					kpi_html +
					"<div class='sad-grid'>" +
					"<div>" + left_col + "</div>" +
					"<div>" + right_col + "</div>" +
					"</div>";

				$body.html(html);
			})
			.catch(function () {
				$body.html("<p class='text-danger' style='padding:20px 0;'>" + __("Impossible de charger le tableau de bord (voir le journal des erreurs).") + "</p>");
			});
	}

	render();
};
