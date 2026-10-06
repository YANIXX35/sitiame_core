// Copyright (c) 2026, Sitiame Capital — License: MIT
// Page "Tableau de Bord" : cockpit récapitulatif pour les clients PME.
// Affiche trésorerie, comptabilité, achats, ventes, stock, scoring + sparklines.

frappe.pages["erp-tableau-de-bord"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Tableau de Bord"),
		single_column: true,
	});

	page.set_secondary_action(__("Actualiser"), load, "refresh");

	// ── CSS inline ─────────────────────────────────────────────────────────
	if (!document.getElementById("tdb-styles")) {
		var style = document.createElement("style");
		style.id = "tdb-styles";
		style.textContent = `
			.tdb-wrap { padding: 0 16px 40px; }
			.tdb-hero {
				background: linear-gradient(135deg,#0f172a 0%,#1e3a5f 60%,#1d4ed8 100%);
				border-radius: 16px; padding: 24px 28px; color:#fff;
				margin-bottom: 20px; position:relative; overflow:hidden;
			}
			.tdb-hero::before {
				content:''; position:absolute; top:-50px; right:-50px;
				width:200px; height:200px; background:rgba(255,255,255,.04); border-radius:50%;
			}
			.tdb-section-title {
				font-size:.68rem; font-weight:800; text-transform:uppercase;
				letter-spacing:.09em; color:#94a3b8; margin:20px 0 10px;
			}
			.tdb-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:12px; margin-bottom:4px; }
			.tdb-card {
				background:#fff; border:1px solid #e2e8f0; border-radius:14px;
				padding:16px; position:relative; overflow:hidden;
				transition: transform .2s, box-shadow .2s;
			}
			.tdb-card:hover { transform:translateY(-2px); box-shadow:0 8px 24px rgba(15,23,42,.08); }
			.tdb-card .tdb-accent {
				position:absolute; top:0; left:0; right:0; height:3px; border-radius:14px 14px 0 0;
			}
			.tdb-label { font-size:.65rem; font-weight:700; text-transform:uppercase; letter-spacing:.07em; color:#94a3b8; margin-bottom:6px; }
			.tdb-val { font-size:1.55rem; font-weight:800; line-height:1; letter-spacing:-.4px; color:#0f172a; }
			.tdb-sub  { font-size:.72rem; color:#64748b; margin-top:4px; }
			.tdb-pill {
				display:inline-flex; align-items:center; gap:4px;
				padding:2px 10px; border-radius:999px; font-size:.68rem; font-weight:700;
			}
			.tdb-pill-ok     { background:#dcfce7; color:#15803d; }
			.tdb-pill-warn   { background:#ffedd5; color:#c2410c; }
			.tdb-pill-err    { background:#fee2e2; color:#b91c1c; }
			.tdb-pill-info   { background:#dbeafe; color:#1d4ed8; }
			.tdb-pill-purple { background:#f3e8ff; color:#7e22ce; }
			.tdb-chart-wrap { height:70px; margin-top:10px; }
			.tdb-score-ring { position:relative; width:80px; height:80px; flex-shrink:0; }
			.tdb-score-ring .score-num {
				position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
				font-size:1.2rem; font-weight:800;
			}
			.tdb-row { display:flex; align-items:center; justify-content:space-between; padding:5px 0; border-bottom:1px solid #f1f5f9; }
			.tdb-row:last-child { border-bottom:none; }
			.tdb-link-btn {
				font-size:.7rem; font-weight:700; padding:4px 12px; border-radius:999px;
				border:1px solid #e2e8f0; background:#f8fafc; color:#334155; cursor:pointer;
				transition:background .15s;
			}
			.tdb-link-btn:hover { background:#e2e8f0; }
			@media(max-width:600px) {
				.tdb-grid { grid-template-columns:repeat(2,1fr); }
				.tdb-val  { font-size:1.2rem; }
			}
		`;
		document.head.appendChild(style);
	}

	var $body = $("<div class='tdb-wrap'></div>").appendTo(page.body);

	function fmt(n) {
		return Number(n || 0).toLocaleString("fr-FR", { maximumFractionDigits: 0 });
	}

	function pill(text, cls) {
		return "<span class='tdb-pill " + (cls || "tdb-pill-info") + "'>" + frappe.utils.escape_html(text) + "</span>";
	}

	function card(label, value, sub, accentColor, extra) {
		return "<div class='tdb-card'>"
			+ "<div class='tdb-accent' style='background:" + accentColor + ";'></div>"
			+ "<div class='tdb-label'>" + label + "</div>"
			+ "<div class='tdb-val'>" + value + "</div>"
			+ (sub ? "<div class='tdb-sub'>" + sub + "</div>" : "")
			+ (extra || "")
			+ "</div>";
	}

	function load() {
		$body.html("<div style='padding:40px;text-align:center;color:#94a3b8;'>"
			+ "<i class='fa fa-spinner fa-spin fa-2x'></i><br><br>Chargement en cours…</div>");

		frappe.call({
			method: "sitiame_core.tableau_de_bord.get_dashboard_data",
			freeze: false,
			callback: function (r) {
				if (r.exc) {
					$body.html("<div style='padding:40px;color:#ef4444;'>Erreur lors du chargement des données.</div>");
					return;
				}
				render(r.message);
			},
		});
	}

	function render(d) {
		$body.empty();
		var t = d.tresorerie, c = d.comptabilite, a = d.achats, v = d.ventes, s = d.scoring, st = d.stock, sp = d.sparklines;
		var solde = flt(t.solde);

		// ── HERO ─────────────────────────────────────────────────────────
		var heroPill = solde >= 0
			? "<span class='tdb-pill tdb-pill-ok' style='background:rgba(16,185,129,.2);color:#6ee7b7;'>✓ Positif</span>"
			: "<span class='tdb-pill tdb-pill-err' style='background:rgba(239,68,68,.2);color:#fca5a5;'>⚠ Négatif</span>";

		$body.append(
			"<div class='tdb-hero'>"
			+ "<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;'>"
			+ "<div>"
			+ "<div style='font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;opacity:.7;'>PME360 · Vue d'ensemble</div>"
			+ "<div style='font-size:1.5rem;font-weight:800;letter-spacing:-.4px;margin:4px 0;'>Tableau de Bord</div>"
			+ "<div style='font-size:.8rem;opacity:.75;'>Trésorerie · Comptabilité · Achats · Ventes · Stock · Scoring</div>"
			+ "</div>"
			+ "<div style='text-align:right;'>"
			+ "<div style='font-size:.68rem;opacity:.7;margin-bottom:4px;'>Trésorerie nette</div>"
			+ "<div style='font-size:1.8rem;font-weight:800;letter-spacing:-1px;'>" + fmt(solde) + " <span style='font-size:.9rem;opacity:.6;'>FCFA</span></div>"
			+ heroPill
			+ "</div>"
			+ "</div>"
			+ "</div>"
		);

		// ── TRÉSORERIE ────────────────────────────────────────────────────
		$body.append("<div class='tdb-section-title'>💰 Trésorerie (mois en cours)</div><div class='tdb-grid tdb-treso-grid'></div>");
		var $treso = $body.find(".tdb-treso-grid");
		$treso.append(card("Encaissements", fmt(t.encaissements_mois) + " <small style='font-size:.8rem;color:#94a3b8;'>FCFA</small>", "Ce mois", "linear-gradient(90deg,#10b981,#34d399)"));
		$treso.append(card("Décaissements", fmt(t.decaissements_mois) + " <small style='font-size:.8rem;color:#94a3b8;'>FCFA</small>", "Ce mois", "linear-gradient(90deg,#ef4444,#f87171)"));
		$treso.append(
			"<div class='tdb-card' style='grid-column:span 2;'>"
			+ "<div class='tdb-accent' style='background:linear-gradient(90deg,#3b82f6,#60a5fa);'></div>"
			+ "<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;'>"
			+ "<div class='tdb-label'>Flux trésorerie 6 mois</div>"
			+ "<button class='tdb-link-btn' onclick=\"frappe.set_route('query-report','General Ledger')\">Grand-Livre →</button>"
			+ "</div>"
			+ "<div class='tdb-chart-wrap'><canvas id='tdb-chart-treso'></canvas></div>"
			+ "</div>"
		);

		// ── COMPTABILITÉ ──────────────────────────────────────────────────
		$body.append("<div class='tdb-section-title'>📒 Comptabilité</div><div class='tdb-grid'></div>");
		var $compta = $body.find(".tdb-grid:last");
		$compta.append(card("Écritures totales", fmt(c.total_ecritures), "Toutes périodes", "linear-gradient(90deg,#6366f1,#818cf8)"));
		$compta.append(card("Volume ce mois", fmt(c.volume_mois) + " <small style='font-size:.8rem;color:#94a3b8;'>FCFA</small>", "Somme des débits", "linear-gradient(90deg,#8b5cf6,#a78bfa)"));
		var lastEntry = c.derniere_ecriture_date
			? pill(c.derniere_ecriture_date, "tdb-pill-info") + " <span style='font-size:.72rem;color:#64748b;'>" + frappe.utils.escape_html(c.derniere_ecriture_ref || "") + "</span>"
			: "<span style='font-size:.72rem;color:#94a3b8;'>Aucune écriture</span>";
		$compta.append(card("Dernière écriture", "", lastEntry, "linear-gradient(90deg,#06b6d4,#22d3ee)",
			"<button class='tdb-link-btn' style='margin-top:8px;' onclick=\"frappe.set_route('query-report','Trial Balance')\">Balance →</button>"));

		// ── ACHATS ────────────────────────────────────────────────────────
		$body.append("<div class='tdb-section-title'>🛒 Achats (mois en cours)</div><div class='tdb-grid'></div>");
		var $ach = $body.find(".tdb-grid:last");
		var achWait = a.en_attente_paiement > 0
			? pill("⚠ " + a.en_attente_paiement + " impayée(s)", "tdb-pill-warn") : pill("✓ À jour", "tdb-pill-ok");
		$ach.append(card("Montant achats", fmt(a.montant_mois) + " <small style='font-size:.8rem;color:#94a3b8;'>FCFA</small>", a.nb_factures_mois + " facture(s) ce mois", "linear-gradient(90deg,#f97316,#fb923c)"));
		$ach.append(
			"<div class='tdb-card'>"
			+ "<div class='tdb-accent' style='background:linear-gradient(90deg,#f59e0b,#fbbf24);'></div>"
			+ "<div class='tdb-label'>Factures fournisseurs</div>"
			+ "<div style='margin-top:8px;'>" + achWait + "</div>"
			+ "<button class='tdb-link-btn' style='margin-top:10px;' onclick=\"frappe.set_route('List','Purchase Invoice')\">Voir factures →</button>"
			+ "</div>"
		);

		// ── VENTES ────────────────────────────────────────────────────────
		$body.append("<div class='tdb-section-title'>📈 Ventes (mois en cours)</div><div class='tdb-grid'></div>");
		var $ven = $body.find(".tdb-grid:last");
		var venImp = v.impayes > 0
			? pill("⚠ " + v.impayes + " impayée(s)", "tdb-pill-err") : pill("✓ Tout encaissé", "tdb-pill-ok");
		$ven.append(card("CA ce mois", fmt(v.ca_mois) + " <small style='font-size:.8rem;color:#94a3b8;'>FCFA</small>", v.nb_factures_mois + " facture(s)", "linear-gradient(90deg,#10b981,#34d399)"));
		$ven.append(card("CA total cumulé", fmt(v.ca_total) + " <small style='font-size:.8rem;color:#94a3b8;'>FCFA</small>", "Depuis le début", "linear-gradient(90deg,#059669,#10b981)"));
		$ven.append(
			"<div class='tdb-card'>"
			+ "<div class='tdb-accent' style='background:linear-gradient(90deg,#10b981,#059669);'></div>"
			+ "<div class='tdb-label'>Recouvrement clients</div>"
			+ "<div style='margin-top:8px;'>" + venImp + "</div>"
			+ "<button class='tdb-link-btn' style='margin-top:10px;' onclick=\"frappe.set_route('List','Sales Invoice')\">Voir factures →</button>"
			+ "</div>"
		);

		// ── GRAPHIQUE VENTES / ACHATS 6 MOIS ────────────────────────────
		$body.append(
			"<div class='tdb-section-title'>📊 Évolution 6 mois — Ventes vs Achats</div>"
			+ "<div class='tdb-card' style='margin-bottom:4px;'>"
			+ "<div class='tdb-accent' style='background:linear-gradient(90deg,#10b981,#3b82f6);'></div>"
			+ "<div class='tdb-chart-wrap' style='height:160px;'><canvas id='tdb-chart-ventes-achats'></canvas></div>"
			+ "</div>"
		);

		// ── STOCK ─────────────────────────────────────────────────────────
		$body.append("<div class='tdb-section-title'>📦 Stock & Inventaire</div><div class='tdb-grid'></div>");
		var $stk = $body.find(".tdb-grid:last");
		$stk.append(card("Valeur du stock", fmt(st.valeur_stock) + " <small style='font-size:.8rem;color:#94a3b8;'>FCFA</small>", "Valorisation totale", "linear-gradient(90deg,#0d9488,#2dd4bf)"));
		$stk.append(card("Articles en stock", fmt(st.nb_articles), "Références avec qty > 0", "linear-gradient(90deg,#0891b2,#22d3ee)",
			"<button class='tdb-link-btn' style='margin-top:8px;' onclick=\"frappe.set_route('List','Item')\">Catalogue →</button>"));

		// ── SCORING ───────────────────────────────────────────────────────
		$body.append("<div class='tdb-section-title'>🏆 Scoring & Financement</div><div class='tdb-grid'></div>");
		var $sc = $body.find(".tdb-grid:last");
		if (s.score_global !== null && s.score_global !== undefined) {
			var sg = flt(s.score_global);
			var scoreColor = sg >= 70 ? "#10b981" : (sg >= 40 ? "#f59e0b" : "#ef4444");
			var scorePill  = sg >= 70 ? pill("Profil solide", "tdb-pill-ok") : (sg >= 40 ? pill("Profil moyen", "tdb-pill-warn") : pill("Profil fragile", "tdb-pill-err"));
			var r = 34, circ = 2 * Math.PI * r, dash = circ * (Math.min(sg, 100) / 100);
			var ring = "<div class='tdb-score-ring'>"
				+ "<svg width='80' height='80' viewBox='0 0 80 80' style='transform:rotate(-90deg);'>"
				+ "<circle cx='40' cy='40' r='" + r + "' fill='none' stroke='#f1f5f9' stroke-width='7'/>"
				+ "<circle cx='40' cy='40' r='" + r + "' fill='none' stroke='" + scoreColor + "' stroke-width='7'"
				+ " stroke-dasharray='" + dash.toFixed(1) + " " + circ.toFixed(1) + "' stroke-linecap='round'/>"
				+ "</svg>"
				+ "<div class='score-num' style='color:" + scoreColor + ";'>" + Math.round(sg) + "</div>"
				+ "</div>";
			$sc.append(
				"<div class='tdb-card' style='display:flex;align-items:center;gap:16px;grid-column:span 2;'>"
				+ "<div class='tdb-accent' style='background:linear-gradient(90deg,#7c3aed,#a78bfa);'></div>"
				+ ring
				+ "<div>"
				+ "<div class='tdb-label'>Score PME360</div>"
				+ "<div class='tdb-val' style='color:" + scoreColor + ";font-size:1.1rem;'>" + sg.toFixed(1) + " / 100</div>"
				+ "<div style='margin-top:6px;'>" + scorePill + "</div>"
				+ (s.statut_dossier ? "<div class='tdb-sub' style='margin-top:4px;'>Dossier : " + frappe.utils.escape_html(s.statut_dossier) + "</div>" : "")
				+ "<button class='tdb-link-btn' style='margin-top:10px;' onclick=\"frappe.set_route('Form','Financing Dossier','" + frappe.utils.escape_html(s.dossier_name || "") + "')\">Voir le dossier →</button>"
				+ "</div>"
				+ "</div>"
			);
		} else {
			$sc.append(
				"<div class='tdb-card' style='grid-column:span 2;'>"
				+ "<div class='tdb-accent' style='background:linear-gradient(90deg,#7c3aed,#a78bfa);'></div>"
				+ "<div class='tdb-label'>Score PME360</div>"
				+ "<div class='tdb-sub' style='margin-top:8px;'>Aucun dossier de financement. Créez-en un pour obtenir votre score d'accès aux investisseurs.</div>"
				+ "<button class='tdb-link-btn' style='margin-top:10px;' onclick=\"frappe.new_doc('Financing Dossier')\">Créer mon dossier →</button>"
				+ "</div>"
			);
		}

		// ── GRAPHIQUES Chart.js ───────────────────────────────────────────
		frappe.require("https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js", function () {
			// Trésorerie sparkline
			var ctxT = document.getElementById("tdb-chart-treso");
			if (ctxT) {
				new Chart(ctxT, {
					type: "line",
					data: {
						labels: sp.labels,
						datasets: [{
							label: "Trésorerie",
							data: sp.tresorerie,
							borderColor: "#3b82f6",
							backgroundColor: "rgba(59,130,246,.08)",
							tension: .4, fill: true, pointRadius: 2,
						}],
					},
					options: {
						responsive: true, maintainAspectRatio: false,
						plugins: { legend: { display: false } },
						scales: { x: { display: false }, y: { display: false, beginAtZero: false } },
					},
				});
			}

			// Ventes vs Achats barres
			var ctxV = document.getElementById("tdb-chart-ventes-achats");
			if (ctxV) {
				new Chart(ctxV, {
					type: "bar",
					data: {
						labels: sp.labels,
						datasets: [
							{ label: "Ventes", data: sp.ventes, backgroundColor: "rgba(16,185,129,.75)", borderRadius: 5 },
							{ label: "Achats", data: sp.achats, backgroundColor: "rgba(239,68,68,.65)", borderRadius: 5 },
						],
					},
					options: {
						responsive: true, maintainAspectRatio: false,
						plugins: { legend: { labels: { boxWidth: 10, font: { size: 11 } } } },
						scales: { y: { beginAtZero: true, ticks: { font: { size: 10 } } }, x: { ticks: { font: { size: 10 } } } },
					},
				});
			}
		});
	}

	load();
};

function flt(v) { return parseFloat(v) || 0; }
