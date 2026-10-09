// Copyright (c) 2026, Sitiame Capital — License: MIT
// Page "Offres PME360" : gestion des offres d'abonnement des clients PME.
// 4 niveaux : Essentiel / Conformite / Pilotage / Transformation
// Tarifs par régime fiscal (TEE/RME/RSI/RNI).
// Accès réservé : System Manager et Administrateur Plateforme Sitiame.

frappe.pages["erp-offres-pme"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Offres PME360"),
		single_column: true,
	});
	page.add_action_item(__("Rafraichir"), function () { render(); });

	const OFFERS = [
		{
			key: "Essentiel",
			color: "#0ea5e9",
			badge: "",
			promise: "Vous tenez votre comptabilite, nous la supervisons.",
			users: "1 utilisateur",
			pieces: "100 pieces/mois",
			prices: { tee: 15000, synth: 25000, reel_s: 50000, reel_n: 80000 },
			features: ["Tableau de bord dirigeant", "Facturation & Achats", "Caisse & Mobile Money", "Stock", "Revue mensuelle SITIAME"],
		},
		{
			key: "Conformite",
			color: "#8b5cf6",
			badge: "RECOMMANDE",
			promise: "Vous saisissez, nous certifions et nous deposons.",
			users: "3 utilisateurs",
			pieces: "200 pieces/mois",
			prices: { tee: 30000, synth: 45000, reel_s: 85000, reel_n: 130000 },
			features: ["Tout Essentiel", "Validation des ecritures", "Depot TVA", "Etats SYSCOHADA", "Cloture mensuelle", "Expert-comptable referent"],
		},
		{
			key: "Pilotage",
			color: "#f59e0b",
			badge: "",
			promise: "Nous tenons votre gestion administrative et financiere.",
			users: "5 utilisateurs",
			pieces: "300 pieces/mois",
			prices: { tee: 75000, synth: 100000, reel_s: 175000, reel_n: 250000 },
			features: ["Tout Conformite", "Tenue complete", "Relances clients", "Tresorerie previsionnelle", "Charge de compte dedie"],
		},
		{
			key: "Transformation",
			color: "#10b981",
			badge: "PREMIUM",
			promise: "Nous digitalisons votre gestion et preparons votre financement.",
			users: "Illimite",
			pieces: "Illimite",
			prices: { tee: 200000, synth: 250000, reel_s: 300000, reel_n: 400000 },
			features: ["Tout Pilotage", "Paie & bulletins", "Immobilisations", "Dossier de financement", "Formation equipes", "Comite trimestriel"],
		},
	];

	const REGIME_LABELS = {
		tee: "Entreprenant/TEE",
		synth: "Impot synth.",
		reel_s: "Reel simplifie",
		reel_n: "Reel normal",
	};

	var $body = $(wrapper).find(".page-content");
	var allRows = [];

	function fmt(v) {
		return v.toLocaleString("fr-FR") + " FCFA";
	}

	function offerColor(o) {
		var c = { "Essentiel": "#0ea5e9", "Conformite": "#8b5cf6", "Pilotage": "#f59e0b", "Transformation": "#10b981" };
		return c[o] || "#6b7280";
	}

	function offerBadge(o) {
		if (!o) return "<span style='color:#9ca3af;font-size:.8rem;'>—</span>";
		var col = offerColor(o);
		return "<span style='background:" + col + "22;color:" + col + ";font-size:.75rem;font-weight:600;padding:3px 10px;border-radius:20px;display:inline-block;'>" + frappe.utils.escape_html(o) + "</span>";
	}

	function regimeBadge(r) {
		var label = REGIME_LABELS[r] || r || "—";
		return "<span style='background:#f3f4f6;color:#6b7280;font-size:.72rem;padding:2px 8px;border-radius:12px;'>" + frappe.utils.escape_html(label) + "</span>";
	}

	function renderTable(rows) {
		var $wrap = $("#erp-offres-pme-table");
		if (!rows.length) {
			$wrap.html("<div style='padding:40px;text-align:center;color:#9ca3af;'>Aucun client PME trouve.</div>");
			return;
		}

		var offerOptions = OFFERS.map(function (o) {
			return "<option value='" + o.key + "'>" + o.key + "</option>";
		}).join("");

		var tbody = rows.map(function (u, i) {
			var o = OFFERS.find(function (x) { return x.key === u.offer; });
			var price = (o && u.regime) ? o.prices[u.regime] : null;
			var priceHtml = price ? "<div style='margin-top:3px;font-size:.75rem;color:#10b981;font-weight:600;'>" + fmt(price) + "/mois</div>" : "";
			var bg = i % 2 === 0 ? "#fff" : "#fafafa";

			return "<tr style='border-bottom:1px solid #f3f4f6;background:" + bg + ";'>" +
				"<td style='padding:12px 16px;'>" +
					"<div style='font-weight:600;color:#111827;font-size:.88rem;'>" + frappe.utils.escape_html(u.full_name || u.user) + "</div>" +
					"<div style='font-size:.75rem;color:#9ca3af;'>" + frappe.utils.escape_html(u.user) + "</div>" +
				"</td>" +
				"<td style='padding:12px 16px;'>" +
					"<div style='font-weight:500;color:#374151;font-size:.85rem;'>" + frappe.utils.escape_html(u.company || "—") + "</div>" +
					"<div style='margin-top:4px;'>" + regimeBadge(u.regime) + "</div>" +
				"</td>" +
				"<td style='padding:12px 16px;'>" +
					offerBadge(u.offer) + priceHtml +
				"</td>" +
				"<td style='padding:12px 16px;'>" +
					"<div style='display:flex;gap:8px;align-items:center;'>" +
						"<select class='erp-offer-select' data-user='" + frappe.utils.escape_html(u.user) + "' " +
							"style='border:1px solid #e5e7eb;border-radius:8px;padding:5px 10px;font-size:.82rem;cursor:pointer;outline:none;'>" +
							"<option value=''>-- Choisir --</option>" + offerOptions +
						"</select>" +
						"<button class='erp-apply-btn' data-user='" + frappe.utils.escape_html(u.user) + "' " +
							"style='background:#111827;color:#fff;border:none;border-radius:8px;padding:6px 14px;font-size:.8rem;cursor:pointer;font-weight:600;white-space:nowrap;'>" +
							"Appliquer" +
						"</button>" +
					"</div>" +
				"</td>" +
			"</tr>";
		}).join("");

		$wrap.html(
			"<table style='width:100%;border-collapse:collapse;'>" +
				"<thead><tr style='background:#f9fafb;border-bottom:2px solid #e5e7eb;'>" +
					"<th style='padding:12px 16px;text-align:left;font-size:.8rem;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.05em;'>Client</th>" +
					"<th style='padding:12px 16px;text-align:left;font-size:.8rem;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.05em;'>Societe & Regime</th>" +
					"<th style='padding:12px 16px;text-align:left;font-size:.8rem;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.05em;'>Offre actuelle</th>" +
					"<th style='padding:12px 16px;text-align:left;font-size:.8rem;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.05em;'>Changer l offre</th>" +
				"</tr></thead>" +
				"<tbody>" + tbody + "</tbody>" +
			"</table>"
		);

		$wrap.find(".erp-apply-btn").on("click", function () {
			var $btn = $(this);
			var user = $btn.data("user");
			var $sel = $wrap.find(".erp-offer-select[data-user='" + user + "']");
			var offer = $sel.val();
			if (!offer) { frappe.msgprint("Selectionnez une offre d abord."); return; }

			$btn.text("...").prop("disabled", true);
			frappe.call({
				method: "sitiame_core.api.apply_offer_to_user",
				args: { user_email: user, offer: offer },
				callback: function (r) {
					if (r.message && r.message.ok) {
						frappe.show_alert({ message: "Offre " + offer + " appliquee a " + user, indicator: "green" });
						// Recharger la table pour refléter le changement
						frappe.call({
							method: "sitiame_core.api.get_pme_users_with_offers",
							callback: function (r2) {
								allRows = r2.message || [];
								var q = $("#erp-offres-pme-search").val().toLowerCase();
								renderTable(q ? allRows.filter(function (u) {
									return (u.user || "").toLowerCase().includes(q) ||
										(u.full_name || "").toLowerCase().includes(q) ||
										(u.company || "").toLowerCase().includes(q);
								}) : allRows);
							},
						});
					} else {
						frappe.msgprint((r.message && r.message.error) ? r.message.error : "Erreur inconnue.");
						$btn.text("Appliquer").prop("disabled", false);
					}
				},
			});
		});
	}

	function render() {
		$body.empty();

		var cardsHtml = OFFERS.map(function (o) {
			var badgeHtml = o.badge ? "<span style='position:absolute;top:12px;right:12px;background:" + o.color + ";color:#fff;font-size:.65rem;font-weight:700;padding:2px 8px;border-radius:20px;'>" + o.badge + "</span>" : "";
			var featHtml = o.features.map(function (f) {
				return "<div style='font-size:.8rem;color:#374151;padding:2px 0;'>&#x2713; " + frappe.utils.escape_html(f) + "</div>";
			}).join("");
			return "<div style='background:#fff;border-radius:14px;box-shadow:0 1px 6px rgba(0,0,0,.08);padding:20px;border-top:4px solid " + o.color + ";position:relative;'>" +
				badgeHtml +
				"<div style='font-size:1.05rem;font-weight:700;color:" + o.color + ";margin-bottom:6px;'>PME360 " + o.key + "</div>" +
				"<div style='font-size:.8rem;color:#6b7280;margin-bottom:12px;min-height:40px;'>" + frappe.utils.escape_html(o.promise) + "</div>" +
				"<div style='font-size:1.4rem;font-weight:800;color:#111827;'>" + fmt(o.prices.synth) + "<span style='font-size:.7rem;font-weight:400;color:#9ca3af;'>/mois*</span></div>" +
				"<div style='font-size:.68rem;color:#9ca3af;margin-bottom:10px;'>*Impot synthetique</div>" +
				"<div style='border-top:1px solid #f3f4f6;padding-top:10px;'>" + featHtml + "</div>" +
				"<div style='margin-top:10px;padding-top:8px;border-top:1px solid #f3f4f6;font-size:.75rem;color:#6b7280;'>" + o.users + " &middot; " + o.pieces + "</div>" +
			"</div>";
		}).join("");

		$body.html(
			"<div style='padding:20px 20px 60px;font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",sans-serif;'>" +
				"<h2 style='font-size:1.3rem;font-weight:700;color:#111827;margin-bottom:4px;'>Gestion des Offres PME360</h2>" +
				"<p style='color:#6b7280;margin-bottom:24px;font-size:.9rem;'>Attribuez une offre a chaque client PME. Les acces et tuiles se mettent a jour automatiquement.</p>" +
				"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin-bottom:28px;'>" + cardsHtml + "</div>" +
				"<div style='background:#fff;border-radius:14px;box-shadow:0 1px 6px rgba(0,0,0,.08);overflow:hidden;'>" +
					"<div style='padding:16px 20px;border-bottom:1px solid #f3f4f6;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;'>" +
						"<h3 style='font-size:1rem;font-weight:700;color:#111827;margin:0;'>Clients PME</h3>" +
						"<input id='erp-offres-pme-search' type='text' placeholder='Rechercher...' " +
							"style='border:1px solid #e5e7eb;border-radius:8px;padding:6px 12px;font-size:.85rem;outline:none;width:200px;'>" +
					"</div>" +
					"<div id='erp-offres-pme-table'><div style='padding:40px;text-align:center;color:#9ca3af;'>Chargement...</div></div>" +
				"</div>" +
			"</div>"
		);

		frappe.call({
			method: "sitiame_core.api.get_pme_users_with_offers",
			callback: function (r) {
				allRows = r.message || [];
				renderTable(allRows);
			},
		});

		$(document).off("input.offres-search").on("input.offres-search", "#erp-offres-pme-search", function () {
			var q = $(this).val().toLowerCase();
			renderTable(q ? allRows.filter(function (u) {
				return (u.user || "").toLowerCase().includes(q) ||
					(u.full_name || "").toLowerCase().includes(q) ||
					(u.company || "").toLowerCase().includes(q);
			}) : allRows);
		});
	}

	render();
};
