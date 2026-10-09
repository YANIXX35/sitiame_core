// Copyright (c) 2026, Sitiame Capital — License: MIT
// Page "Offres PME360" : gestion des offres d'abonnement des clients PME.
// Affiche les 3 niveaux d'offre, liste les comptes PME actifs,
// et permet à l'administrateur de changer l'offre d'un client.

frappe.pages["erp-offres-pme"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Offres PME360"),
		single_column: true,
	});

	page.set_secondary_action(__("Actualiser"), load, "refresh");

	// ── CSS inline ─────────────────────────────────────────────────────────
	if (!document.getElementById("offres-pme-styles")) {
		var style = document.createElement("style");
		style.id = "offres-pme-styles";
		style.textContent = `
			.offres-wrap { padding: 0 16px 40px; }
			.offres-hero {
				background: linear-gradient(135deg,#0f172a 0%,#1e3a5f 60%,#1d4ed8 100%);
				border-radius: 16px; padding: 24px 28px; color:#fff;
				margin-bottom: 20px; position:relative; overflow:hidden;
			}
			.offres-hero h2 { margin:0 0 4px; font-size:1.3rem; font-weight:700; }
			.offres-hero p  { margin:0; opacity:.75; font-size:.9rem; }
			.offres-section-title {
				font-size:.68rem; font-weight:800; text-transform:uppercase;
				letter-spacing:.09em; color:#94a3b8; margin:20px 0 10px;
			}
			.offres-cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:14px; margin-bottom:24px; }
			.offre-card {
				background:#fff; border:2px solid #e2e8f0; border-radius:14px;
				padding:20px; transition: transform .2s, box-shadow .2s, border-color .2s;
			}
			.offre-card:hover { transform:translateY(-2px); box-shadow:0 8px 24px rgba(15,23,42,.08); }
			.offre-card.active { border-color:#1d4ed8; }
			.offre-card .offre-badge {
				display:inline-block; font-size:.65rem; font-weight:700; text-transform:uppercase;
				letter-spacing:.08em; padding:3px 10px; border-radius:20px; margin-bottom:10px;
			}
			.offre-essentiel    .offre-badge { background:#e0f2fe; color:#0369a1; }
			.offre-pilotage     .offre-badge { background:#ede9fe; color:#6d28d9; }
			.offre-transformation .offre-badge { background:#fef3c7; color:#b45309; }
			.offre-card h3  { font-size:1.1rem; font-weight:700; margin:0 0 6px; color:#0f172a; }
			.offre-card .offre-price { font-size:1.6rem; font-weight:800; color:#1d4ed8; margin:0 0 10px; }
			.offre-card .offre-price small { font-size:.75rem; font-weight:400; color:#64748b; }
			.offre-card ul { padding-left:1.1em; margin:0; color:#475569; font-size:.82rem; line-height:1.7; }
			.offres-table-wrap { background:#fff; border:1px solid #e2e8f0; border-radius:14px; overflow:hidden; }
			.offres-table { width:100%; border-collapse:collapse; font-size:.83rem; }
			.offres-table th {
				background:#f8fafc; padding:10px 14px; text-align:left;
				font-size:.68rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em;
				color:#64748b; border-bottom:1px solid #e2e8f0;
			}
			.offres-table td { padding:10px 14px; border-bottom:1px solid #f1f5f9; vertical-align:middle; }
			.offres-table tr:last-child td { border-bottom:none; }
			.offres-table tr:hover td { background:#f8fafc; }
			.offre-tag {
				display:inline-block; font-size:.68rem; font-weight:600; padding:2px 10px;
				border-radius:12px; text-transform:uppercase; letter-spacing:.05em;
			}
			.offre-tag-essentiel    { background:#e0f2fe; color:#0369a1; }
			.offre-tag-pilotage     { background:#ede9fe; color:#6d28d9; }
			.offre-tag-transformation { background:#fef3c7; color:#b45309; }
			.offre-select { font-size:.82rem; padding:4px 8px; border:1px solid #cbd5e1; border-radius:6px; }
			.offre-apply-btn {
				font-size:.78rem; padding:5px 14px; background:#1d4ed8; color:#fff;
				border:none; border-radius:6px; cursor:pointer; margin-left:6px;
				transition: background .15s;
			}
			.offre-apply-btn:hover { background:#1e40af; }
			.offres-empty { padding:40px; text-align:center; color:#94a3b8; }
		`;
		document.head.appendChild(style);
	}

	// ── Structure HTML ─────────────────────────────────────────────────────
	$(wrapper).find(".page-content").html(`
		<div class="offres-wrap">
			<div class="offres-hero">
				<h2>${__("Gestion des offres PME360")}</h2>
				<p>${__("Modifiez l'offre d'abonnement de chaque client PME. Le changement prend effet immédiatement.")}</p>
			</div>

			<div class="offres-section-title">${__("Niveaux d'offre disponibles")}</div>
			<div class="offres-cards">
				<div class="offre-card offre-essentiel">
					<span class="offre-badge">Essentiel</span>
					<h3>Essentiel</h3>
					<div class="offre-price">25 000 <small>FCFA / mois</small></div>
					<ul>
						<li>Facturation et devis</li>
						<li>Suivi des achats</li>
						<li>Comptabilité de base</li>
						<li>Supervision SITIAME</li>
					</ul>
				</div>
				<div class="offre-card offre-pilotage">
					<span class="offre-badge">Pilotage</span>
					<h3>Pilotage</h3>
					<div class="offre-price">100 000 <small>FCFA / mois</small></div>
					<ul>
						<li>Tout l'Essentiel</li>
						<li>Gestion RH et paie</li>
						<li>Immobilisations</li>
						<li>SITIAME tient la gestion admin et financière</li>
					</ul>
				</div>
				<div class="offre-card offre-transformation">
					<span class="offre-badge">Transformation</span>
					<h3>Transformation</h3>
					<div class="offre-price">250 000 <small>FCFA / mois</small></div>
					<ul>
						<li>Tout le Pilotage</li>
						<li>Budget et pilotage prévisionnel</li>
						<li>Dossier de financement</li>
						<li>Digitalisation complète + accompagnement</li>
					</ul>
				</div>
			</div>

			<div class="offres-section-title">${__("Clients PME actifs")}</div>
			<div class="offres-table-wrap">
				<table class="offres-table">
					<thead>
						<tr>
							<th>${__("Utilisateur")}</th>
							<th>${__("Société")}</th>
							<th>${__("Régime fiscal")}</th>
							<th>${__("Offre actuelle")}</th>
							<th>${__("Changer l'offre")}</th>
						</tr>
					</thead>
					<tbody id="offres-tbody">
						<tr><td colspan="5" class="offres-empty">${__("Chargement…")}</td></tr>
					</tbody>
				</table>
			</div>
		</div>
	`);

	load();

	function load() {
		frappe.call({
			method: "sitiame_core.api.get_pme_users_with_offers",
			callback: function (r) {
				render(r.message || []);
			},
			error: function () {
				$("#offres-tbody").html(
					`<tr><td colspan="5" class="offres-empty">${__("Erreur lors du chargement.")}</td></tr>`
				);
			},
		});
	}

	function offreTag(offer) {
		var slug = (offer || "essentiel").toLowerCase();
		return `<span class="offre-tag offre-tag-${slug}">${offer || "Essentiel"}</span>`;
	}

	var OFFERS = ["Essentiel", "Pilotage", "Transformation"];

	function render(rows) {
		if (!rows.length) {
			$("#offres-tbody").html(
				`<tr><td colspan="5" class="offres-empty">${__("Aucun client PME actif.")}</td></tr>`
			);
			return;
		}
		var html = rows.map(function (row) {
			var opts = OFFERS.map(function (o) {
				var sel = o === (row.offer || "Essentiel") ? " selected" : "";
				return `<option value="${o}"${sel}>${o}</option>`;
			}).join("");
			return `
				<tr>
					<td>
						<strong>${frappe.utils.escape_html(row.full_name || row.user)}</strong>
						<br/><small style="color:#94a3b8">${frappe.utils.escape_html(row.user)}</small>
					</td>
					<td>${frappe.utils.escape_html(row.company || "—")}</td>
					<td>${frappe.utils.escape_html(row.regime_fiscal || "—")}</td>
					<td>${offreTag(row.offer)}</td>
					<td>
						<select class="offre-select" data-user="${frappe.utils.escape_html(row.user)}"
							data-company="${frappe.utils.escape_html(row.company)}">${opts}</select>
						<button class="offre-apply-btn"
							data-user="${frappe.utils.escape_html(row.user)}">${__("Appliquer")}</button>
					</td>
				</tr>`;
		}).join("");
		$("#offres-tbody").html(html);

		// Event delegation pour les boutons Appliquer
		$("#offres-tbody").off("click.offres").on("click.offres", ".offre-apply-btn", function () {
			var user = $(this).data("user");
			var offer = $(this).closest("td").find(".offre-select").val();
			applyOffer(user, offer, $(this));
		});
	}

	function applyOffer(user, offer, $btn) {
		$btn.prop("disabled", true).text(__("…"));
		frappe.call({
			method: "sitiame_core.api.apply_offer_to_user",
			args: { user: user, offer: offer },
			callback: function (r) {
				$btn.prop("disabled", false).text(__("Appliquer"));
				if (r && r.message && r.message.offer) {
					frappe.show_alert({
						message: __("Offre mise à jour : {0} → {1}", [r.message.company, r.message.offer]),
						indicator: "green",
					}, 4);
					// Mettre à jour la tuile offre actuelle dans la ligne
					var $row = $btn.closest("tr");
					$row.find("td:nth-child(4)").html(offreTag(r.message.offer));
				}
			},
			error: function () {
				$btn.prop("disabled", false).text(__("Appliquer"));
				frappe.show_alert({ message: __("Erreur lors du changement d'offre."), indicator: "red" }, 5);
			},
		});
	}
};
