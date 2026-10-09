// Copyright (c) 2026, Sitiame Capital
// License: MIT

frappe.pages["erp-abonnement"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Abonnement SITIAME"),
		single_column: true,
	});

	var $container = $(
		"<div style='max-width: 580px; margin: 30px auto; padding: 35px 25px; background: #ffffff; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.06); text-align: center; font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif;'>" +
			"<div style='font-size: 46px; margin-bottom: 12px;'>\uD83D\uDCB3</div>" +
			"<h3 style='font-weight: 700; color: #0f172a; margin-bottom: 6px; font-size: 22px;'>" + __("Abonnement PME360") + "</h3>" +
			"<div id='abonnement-offer-badge' style='display:inline-block;margin-bottom:8px;padding:3px 14px;border-radius:99px;font-size:.78rem;font-weight:700;background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;'></div>" +
			"<p style='color: #64748b; font-size: 14px; margin-bottom: 25px;' id='abonnement-price-line'>" +
				__("Abonnement mensuel : <strong><span class='abonnement-price'>\u2014</span> FCFA</strong> / mois<br><span style='font-size: 13px; color: #94a3b8;'>Mobile Money : Wave, Orange Money, MTN, Moov, Djamo</span>") +
			"</p>" +
			"<div id='abonnement-devis-notice' style='display:none;margin-bottom:20px;padding:14px 18px;background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;color:#c2410c;font-size:14px;font-weight:500;'>" +
				"\uD83D\uDCDE " + __("Votre offre Transformation n\u00E9cessite un devis personnalis\u00E9.") + "<br>" +
				"<a href='mailto:contact@sitiame-capital.com' style='color:#ea580c;font-weight:700;'>contact@sitiame-capital.com</a>" +
			"</div>" +

			// Grille informative : prix de toutes les offres (actuellement sélectionnée mise en évidence)
			"<div id='abonnement-offres-grid' style='margin:0 0 20px;display:none;'></div>" +

			// State: Loading
			"<div id='abonnement-state-loading' style='padding: 20px 0;'>" +
				"<div class='spinner-border text-primary' role='status' style='width: 3rem; height: 3rem; margin-bottom: 15px;'></div>" +
				"<div id='abonnement-loading-text' style='font-size: 16px; font-weight: 600; color: #1e293b;'>" + __("Chargement...") + "</div>" +
			"</div>" +

			// State: pick the offer then the operator
			"<div id='abonnement-state-choose' style='display: none; padding: 6px 0;'>" +
				"<div id='abonnement-offre-select' style='margin-bottom:16px;display:none;'>" +
					"<div style='font-size:14px;font-weight:600;color:#1e293b;margin-bottom:10px;'>" + __("Choisissez votre offre") + "</div>" +
					"<div class='abonnement-offres-buttons' style='display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;'></div>" +
					"<div id='abonnement-selected-price' style='margin-top:10px;font-size:13px;color:#475569;min-height:18px;'></div>" +
				"</div>" +
				"<div style='font-size: 15px; font-weight: 600; color: #1e293b; margin-bottom: 14px;'>" + __("Choisissez votre moyen de paiement") + "</div>" +
				"<div class='abonnement-methods' style='display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px;'></div>" +
				"<div style='font-size: 12px; color: #94a3b8; margin-top: 14px;'>" + __("Vous serez redirig\u00e9 vers votre application de paiement, puis ramen\u00e9 ici.") + "</div>" +
			"</div>" +

			// State: Direct Link Ready
			"<div id='abonnement-state-ready' style='display: none; margin-top: 20px;'>" +
				"<a id='btn-payment-direct' href='#' target='_self' class='btn btn-primary btn-lg' style='padding: 12px 32px; font-size: 15px; font-weight: 600; border-radius: 8px; text-decoration: none; display: inline-block; box-shadow: 0 4px 12px rgba(37,99,235,0.25);'>" +
					__("Continuer vers le paiement") +
				"</a>" +
				"<div style='font-size: 12px; color: #94a3b8; margin-top: 12px;'>" + __("Si la redirection automatique ne d\u00e9marre pas, cliquez sur le bouton ci-dessus.") + "</div>" +
			"</div>" +

			// State: back from the operator, not confirmed yet
			"<div id='abonnement-state-pending' style='display: none; padding: 20px 0;'>" +
				"<div style='font-size: 18px; font-weight: 700; color: #b45309; margin-bottom: 8px;'>" + __("Paiement en cours de confirmation") + "</div>" +
				"<div style='font-size: 13px; color: #64748b; margin-bottom: 20px; line-height: 1.5;'>" + __("L'op\u00e9rateur n'a pas encore confirm\u00e9 le paiement. Votre abonnement sera activ\u00e9 automatiquement d\u00e8s la confirmation.") + "</div>" +
				"<button id='btn-check-again' class='btn btn-default' style='border-radius: 8px; padding: 10px 22px;'>" + __("V\u00e9rifier \u00e0 nouveau") + "</button>" +
			"</div>" +

			// State: Already subscribed
			"<div id='abonnement-state-active' style='display: none; padding: 20px 0;'>" +
				"<div style='font-size: 20px; font-weight: 700; color: #15803d; margin-bottom: 8px;'>" + __("Abonnement actif") + "</div>" +
				"<div id='abonnement-active-desc' style='font-size: 14px; color: #475569; margin-bottom: 25px; line-height: 1.5;'></div>" +
				"<button id='btn-extend-subscription' class='btn btn-primary' style='border-radius: 8px; padding: 11px 24px; font-weight: 600;'>" +
					__("Prolonger d'un mois") + " (<span class='abonnement-price'>—</span> FCFA)" +
				"</button>" +
			"</div>" +

			// State: Success
			"<div id='abonnement-state-success' style='display: none; padding: 20px 0;'>" +
				"<div style='font-size: 52px; color: #16a34a; margin-bottom: 12px;'>\u2705</div>" +
				"<div style='font-size: 20px; font-weight: 700; color: #15803d; margin-bottom: 8px;'>" + __("Paiement valid\u00e9 avec succ\u00e8s !") + "</div>" +
				"<div id='abonnement-success-desc' style='font-size: 14px; color: #475569; margin-bottom: 25px; line-height: 1.5;'>" + __("Votre abonnement Enterprise est actif.") + "</div>" +
				"<div style='display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;'>" +
					"<button id='btn-download-receipt' class='btn btn-default' style='border-radius: 8px; padding: 10px 22px; font-weight: 600;'>" + __("T\u00e9l\u00e9charger le re\u00e7u") + "</button>" +
					"<button id='btn-return-desk-success' class='btn btn-primary' style='border-radius: 8px; padding: 10px 26px; font-weight: 600;'>" + __("Acc\u00e9der \u00e0 mon espace Desk") + "</button>" +
				"</div>" +
			"</div>" +

			// State: Failed / Canceled / Expired
			"<div id='abonnement-state-failed' style='display: none; padding: 20px 0;'>" +
				"<div style='font-size: 52px; color: #dc2626; margin-bottom: 12px;'>\u274C</div>" +
				"<div style='font-size: 19px; font-weight: 700; color: #991b1b; margin-bottom: 8px;'>" + __("Le paiement n'a pas pu aboutir") + "</div>" +
				"<div style='font-size: 13px; color: #64748b; margin-bottom: 22px; line-height: 1.5;'>" +
					__("La transaction a \u00e9t\u00e9 annul\u00e9e ou interrompue (d\u00e9lai d\u00e9pass\u00e9, solde insuffisant ou rejet op\u00e9rateur).<br>Votre compte n'a pas \u00e9t\u00e9 d\u00e9bit\u00e9.") +
				"</div>" +
				"<div style='display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;'>" +
					"<button id='btn-retry-payment' class='btn btn-primary' style='border-radius: 8px; padding: 11px 24px; font-weight: 600;'>" +
						__("Relancer le paiement (Nouveau lien)") +
					"</button>" +
					"<button id='btn-return-desk-failed' class='btn btn-outline-secondary' style='border-radius: 8px; padding: 11px 20px; font-weight: 500;'>" +
						__("Retour \u00e0 l'accueil") +
					"</button>" +
				"</div>" +
			"</div>" +

			// State: Generic Error
			"<div id='abonnement-state-error' style='display: none; padding: 16px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 10px; color: #b91c1c; font-size: 14px; margin-top: 15px;'>" +
			"</div>" +
		"</div>"
	).appendTo(page.body);

	// The PME's paid payments, each with its PDF receipt
	var $receipts = $(
		"<div style='max-width: 580px; margin: 0 auto 30px; padding: 22px 25px; background: #ffffff; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.06); display: none;'>" +
			"<h5 style='font-weight: 700; color: #0f172a; margin: 0 0 12px;'>" + __("Mes reçus de paiement") + "</h5>" +
			"<div class='abonnement-receipts' style='overflow-x: auto;'></div>" +
		"</div>"
	).appendTo(page.body);

	// Fetch subscription info: offer name, price, devis flag.
	frappe.call({ method: "sitiame_core.subscription_api.get_my_subscription" }).then(function (r) {
		var msg = r.message || {};
		var offer = msg.offer || "Essentiel";
		var amount = msg.amount;
		var is_devis = msg.is_devis;

		// Badge offre
		$("#abonnement-offer-badge").text(offer).show();
		// Grille tarifaire informative (toujours visible)
		_renderOffresGrid(offer, msg.regime || "TEE");

		if (is_devis) {
			// Offre sur devis : cacher le flux de paiement, afficher la notice
			$("#abonnement-price-line").hide();
			$("#abonnement-devis-notice").show();
			// Bloquer les boutons de paiement
			$("#btn-extend-subscription, #btn-retry-payment").prop("disabled", true).css("opacity", "0.4");
		} else if (amount) {
			$(".abonnement-price").text(format_number(amount, null, 0));
		}
	});

	function receiptUrl(docname) {
		return "/api/method/sitiame_core.subscription_api.download_receipt?docname=" + encodeURIComponent(docname);
	}

	function loadReceipts(company) {
		frappe.call({ method: "sitiame_core.subscription_api.list_my_receipts", args: { company: company || null } }).then(function (r) {
			var rows = r.message || [];
			if (!rows.length) return;
			var html = "<table class='table table-sm' style='font-size: 13px; margin: 0;'><thead><tr>" +
				"<th>" + __("N°") + "</th><th>" + __("Date") + "</th><th style='text-align: right;'>" + __("Montant") + "</th><th></th>" +
				"</tr></thead><tbody>";
			rows.forEach(function (row) {
				html += "<tr><td>" + frappe.utils.escape_html(row.name) + "</td>" +
					"<td>" + (row.paid_at ? frappe.datetime.str_to_user(row.paid_at) : "") + "</td>" +
					"<td style='text-align: right;'>" + format_number(row.amount, null, 0) + " FCFA</td>" +
					"<td style='text-align: right;'><a class='btn btn-xs btn-default' href='" + receiptUrl(row.name) + "'>" + __("Reçu PDF") + "</a></td></tr>";
			});
			$receipts.find(".abonnement-receipts").html(html + "</tbody></table>");
			$receipts.show();
		});
	}

	var paidDocname = null;
	$("#btn-download-receipt").on("click", function () {
		if (paidDocname) window.location.href = receiptUrl(paidDocname);
	});

	function getQueryParam(key) {
		var sp = new URLSearchParams(window.location.search);
		if (sp.has(key)) return sp.get(key);
		if (window.location.hash && window.location.hash.indexOf("?") !== -1) {
			var hashQuery = window.location.hash.split("?")[1];
			var hp = new URLSearchParams(hashQuery);
			if (hp.has(key)) return hp.get(key);
		}
		return null;
	}

	$("#btn-return-desk-success, #btn-return-desk-failed").on("click", function () {
		frappe.set_route("app");
	});

	var LOGOS = "/assets/sitiame_core/images/payment/";

	// Grille tarifaire mensuelle (FCFA) miroir de subscription_api._TARIF
	var _TARIF_JS = {
		"TEE": [15000, 75000, null],
		"RME": [25000, 100000, null],
		"RSI": [50000, 175000, 250000],
		"RNI": [80000, 250000, 400000],
	};
	var _OFFRES_DEF = [
		{ key: "Essentiel",      label: "Essentiel",      color: "#0ea5e9" },
		{ key: "Pilotage",       label: "Pilotage",       color: "#8b5cf6" },
		{ key: "Transformation", label: "Transformation", color: "#f59e0b" },
	];
	var selectedOffer = null;  // initialisé depuis get_my_subscription
	var currentRegime = "";    // régime fiscal de la PME

	var METHODS = [
		{ value: "wave", label: "Wave", color: "#1dc8f2", logo: "wave.png" },
		{ value: "orange", label: "Orange Money", color: "#ff7900", logo: "orange.png" },
		// MTN's logo is wide: shown whole on its own yellow
		{ value: "mtn", label: "MTN MoMo", color: "#ffcb05", logo: "mtn.png", fit: "contain" },
		{ value: "moov", label: "Moov Money", color: "#0066b3", logo: "moov.jpg" },
		{ value: "djamo", label: "Djamo", color: "#111827", logo: "djamo.png" },
	];
	var $methods = $container.find(".abonnement-methods");
	METHODS.forEach(function (m) {
		$("<button class='btn btn-default'></button>")
			.css({
				padding: "10px 12px", "border-radius": "10px", "font-weight": 600, "border-left": "5px solid " + m.color,
				display: "flex", "align-items": "center", gap: "10px", "justify-content": "flex-start",
			})
			.append(
				$("<img>")
					.attr({ src: LOGOS + m.logo, alt: m.label })
					.css({
						width: "40px", height: "40px", "border-radius": "8px", "flex-shrink": 0,
						"object-fit": m.fit || "cover", background: m.color,
					})
			)
			.append($("<span></span>").text(m.label))
			.on("click", function () {
				requestAndRedirect(m.value);
			})
			.appendTo($methods);
	});

	function showOnly(state) {
		$container.find("[id^='abonnement-state-']").hide();
		$("#abonnement-state-" + state).show();
	}

	function showLoading(text) {
		$("#abonnement-loading-text").text(text);
		showOnly("loading");
	}

	$("#btn-extend-subscription, #btn-retry-payment").on("click", function () {
		showOnly("choose");
		if (!staffMode) renderOffreButtons(selectedOffer, currentRegime);
	});

	function endsOnText(sub) {
		if (!sub || !sub.ends_on) return "";
		return __("Actif jusqu'au <strong>{0}</strong>.", [frappe.datetime.str_to_user(sub.ends_on)]);
	}

	function showPaid(data) {
		paidDocname = data.docname || returnDocname;
		$("#btn-download-receipt").toggle(!!paidDocname);
		// staff paid for a PME: that PME's receipts
		loadReceipts(data.company);
		if (data.company) {
			$("#abonnement-success-desc").html(__("Votre abonnement Enterprise est actif pour la soci\u00e9t\u00e9 <strong>{0}</strong>.", [frappe.utils.escape_html(data.company)]) + " " + endsOnText(data.subscription));
		}
		showOnly("success");
	}

	var returnDocname = getQueryParam("docname");
	var returnStatus = (getQueryParam("payment_status") || "").toLowerCase();

	// Back from J\u00e8ko: the operator may confirm a few seconds after the
	// redirect, so check again for a short while before saying "pending".
	function checkReturn(attempt) {
		frappe.call({
			method: "sitiame_core.subscription_api.check_pme_subscription_status",
			args: { docname: returnDocname },
		}).then(function (r) {
			var data = r.message || {};
			if (data.status === "Pay\u00e9") {
				showPaid(data);
			} else if (data.status === "\u00c9chou\u00e9" || returnStatus === "failed") {
				// errorUrl: cancelled or refused at the operator
				showOnly("failed");
			} else if (attempt < 6) {
				setTimeout(function () { checkReturn(attempt + 1); }, 5000);
			} else {
				showOnly("pending");
			}
		}).catch(function () {
			showOnly("pending");
		});
	}

	$("#btn-check-again").on("click", function () {
		showLoading(__("V\u00e9rification du paiement..."));
		checkReturn(6);
	});

	if (returnDocname) {
		showLoading(__("V\u00e9rification du paiement..."));
		checkReturn(0);
	} else {
		frappe.call({
			method: "sitiame_core.subscription_api.get_my_subscription",
		}).then(function (r) {
			var sub = r.message || {};
			// Mémoriser l'offre et le régime pour le sélecteur d'offre
			selectedOffer = sub.offer || "Essentiel";
			currentRegime = sub.regime || "";
			if (!sub.company && sub.is_admin) {
				$container.hide();
				renderAdminPanel();
			} else if (!sub.company && sub.is_staff) {
				// chargé d'affaires, accountants: the PME view, picking the PME first
				setupStaffCompanyPicker();
				showOnly("choose");
				// pas de sélecteur d'offre pour le staff (il n'est pas la PME)
			} else if (!sub.company) {
				showOnly("error");
				$("#abonnement-state-error").html(__("Cette page est réservée aux comptes PME : aucune société n'est rattachée à votre compte. Connectez-vous avec le compte de la PME pour payer son abonnement."));
			} else if (sub.active) {
				loadReceipts();
				$("#abonnement-active-desc").html(endsOnText(sub));
				showOnly("active");
			} else {
				// an expired PME keeps its past receipts
				loadReceipts();
				showOnly("choose");
				renderOffreButtons(selectedOffer, currentRegime);
			}
		}).catch(function () {
			showOnly("choose");
		});
	}

	// Sitiame staff: generate a checkout link for any PME (to send it to
	// them) and see every PME's subscription state.
	function renderAdminPanel() {
		var $admin = $(
			"<div style='max-width: 1000px; margin: 24px auto; padding: 0 16px;'>" +
				"<div style='background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); padding: 20px 22px; margin-bottom: 20px;'>" +
					"<h4 style='font-weight: 700; margin: 0 0 4px;'>" + __("Générer un lien de paiement") + "</h4>" +
					"<p style='color: #64748b; font-size: 13px; margin-bottom: 12px;'>" + __("Choisissez la PME, générez le lien Jèko (1 mois, à usage unique) et envoyez-le-lui : elle choisira son opérateur en l'ouvrant.") + "<br><span style='font-size:13px;'>" + __("Montant selon l'offre :") + " <strong id='admin-prix-par-offre' style='color:#0f172a;'>—</strong></span>" + "</p>" +
					"<div style='display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap;'>" +
						"<div class='admin-company-field' style='min-width: 280px; flex: 1;'></div>" +
						"<button class='btn btn-primary btn-generate-link' style='margin-bottom: 15px;'>" + __("Générer le lien") + "</button>" +
					"</div>" +
					"<div class='admin-link-result' style='display: none; margin-top: 4px;'>" +
						"<div style='display: flex; gap: 8px; flex-wrap: wrap;'>" +
							"<input class='form-control admin-link-input' readonly style='flex: 1; min-width: 260px;'>" +
							"<button class='btn btn-default btn-copy-link'>" + __("Copier") + "</button>" +
							"<a class='btn btn-default btn-open-link' target='_blank'>" + __("Ouvrir") + "</a>" +
						"</div>" +
						"<div class='admin-link-doc' style='font-size: 12px; color: #64748b; margin-top: 6px;'></div>" +
					"</div>" +
				"</div>" +
				"<div style='background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); padding: 20px 22px;'>" +
					"<h4 style='font-weight: 700; margin: 0 0 12px;'>" + __("Abonnements des PME") + "</h4>" +
					"<div class='admin-subscriptions' style='overflow-x: auto;'>" + __("Chargement...") + "</div>" +
				"</div>" +
			"</div>"
		).appendTo(page.body);

		var companyField = frappe.ui.form.make_control({
			parent: $admin.find(".admin-company-field"),
			df: {
				fieldtype: "Link",
				options: "Company",
				label: __("Société (PME)"),
				get_query: function () {
					return { filters: { name: ["!=", "SITIAME"] } };
				},
				change: function () {
					var company = this.get_value();
					if (!company) {
						$("#admin-prix-par-offre").text("—");
						return;
					}
					frappe.call({
						method: "sitiame_core.subscription_api.get_company_subscription_for",
						args: { company: company },
					}).then(function (r) {
						var sub = r.message || {};
						var _IDX = { "Essentiel": 0, "Pilotage": 1, "Transformation": 2 };
						var tarifs = _TARIF_JS[sub.regime] || _TARIF_JS["TEE"];
						var idx = _IDX[sub.offer] !== undefined ? _IDX[sub.offer] : 0;
						var prix = tarifs[idx];
						var priceStr = prix
							? format_number(prix, null, 0) + " FCFA — " + (sub.offer || "Essentiel") + " / " + (sub.regime || "TEE")
							: __("Sur devis (Transformation)");
						$("#admin-prix-par-offre").text(priceStr);
					});
				},
			},
			render_input: true,
		});

		$admin.find(".btn-generate-link").on("click", function () {
			var company = companyField.get_value();
			if (!company) {
				frappe.msgprint(__("Choisissez d'abord une société."));
				return;
			}
			frappe.call({
				method: "sitiame_core.subscription_api.create_company_payment_link",
				args: { company: company },
				freeze: true,
				freeze_message: __("Génération du lien Jèko..."),
			}).then(function (r) {
				var res = r.message || {};
				if (!res.payment_url) {
					frappe.msgprint(__("Jèko n'a pas renvoyé de lien. Voir le journal des erreurs."));
					return;
				}
				$admin.find(".admin-link-input").val(res.payment_url);
				$admin.find(".btn-open-link").attr("href", res.payment_url);
				$admin.find(".admin-link-doc").text(__("Paiement {0} créé pour {1}.", [res.docname, res.company]));
				$admin.find(".admin-link-result").show();
				loadSubscriptions();
			});
		});

		$admin.find(".btn-copy-link").on("click", function () {
			frappe.utils.copy_to_clipboard($admin.find(".admin-link-input").val());
		});

		var STATE_COLORS = { "Actif": "green", "Essai": "orange", "Expiré": "red", "Aucun": "gray" };

		function formatDate(value) {
			return value ? frappe.datetime.str_to_user(value) : "-";
		}

		function loadSubscriptions() {
			frappe.call({ method: "sitiame_core.subscription_api.list_company_subscriptions" }).then(function (r) {
				var rows = r.message || [];
				if (!rows.length) {
					$admin.find(".admin-subscriptions").html("<p style='color: #64748b;'>" + __("Aucune PME.") + "</p>");
					return;
				}
				var html = "<table class='table table-bordered' style='font-size: 13px; margin: 0;'><thead><tr>" +
					"<th>" + __("Société") + "</th><th>" + __("Statut") + "</th><th>" + __("Actif jusqu'au") + "</th>" +
					"<th>" + __("Fin d'essai") + "</th><th>" + __("Paiements") + "</th><th>" + __("Dernier paiement") + "</th>" +
					"</tr></thead><tbody>";
				rows.forEach(function (row) {
					html += "<tr>" +
						"<td>" + frappe.utils.escape_html(row.company) + "</td>" +
						"<td><span class='indicator-pill " + (STATE_COLORS[row.state] || "gray") + "'>" + __(row.state) + "</span></td>" +
						"<td>" + formatDate(row.ends_on) + "</td>" +
						"<td>" + formatDate(row.trial_ends_on) + "</td>" +
						"<td>" + row.paid_count + "</td>" +
						"<td>" + (row.last_paid_at ? frappe.datetime.str_to_user(row.last_paid_at) : "-") + "</td>" +
						"</tr>";
				});
				html += "</tbody></table>";
				$admin.find(".admin-subscriptions").html(html);
			});
		}

		loadSubscriptions();
	}

	// Staff without a company of their own: which PME they pay for
	var staffMode = false;
	var staffCompany = null;

	function setupStaffCompanyPicker() {
		staffMode = true;
		var $picker = $(
			"<div style='text-align: left; margin-bottom: 18px;'>" +
				"<div class='staff-company-field'></div>" +
				"<div class='staff-company-status' style='font-size: 13px; color: #475569; margin-top: -6px;'></div>" +
			"</div>"
		).prependTo($("#abonnement-state-choose"));

		frappe.ui.form.make_control({
			parent: $picker.find(".staff-company-field"),
			df: {
				fieldtype: "Link",
				options: "Company",
				label: __("Soci\u00e9t\u00e9 (PME) \u00e0 abonner"),
				placeholder: __("Choisissez la PME"),
				get_query: function () {
					return { filters: { name: ["!=", "SITIAME"] } };
				},
				change: function () {
					var company = this.get_value();
					if (company === staffCompany) return;
					staffCompany = company || null;
					$receipts.hide();
					var $status = $picker.find(".staff-company-status").empty();
					if (!staffCompany) return;
					frappe.call({
						method: "sitiame_core.subscription_api.get_company_subscription_for",
						args: { company: staffCompany },
					}).then(function (r) {
						var sub = r.message || {};
						if (sub.active) {
							$status.html("<span style='color: #15803d; font-weight: 600;'>" + __("Abonnement actif") + "</span> \u2014 " + endsOnText(sub) + " " + __("Un paiement le prolonge d'un mois."));
						} else if (sub.in_trial) {
							$status.html("<span style='color: #b45309; font-weight: 600;'>" + __("En p\u00e9riode d'essai") + "</span>");
						} else {
							$status.html("<span style='color: #b91c1c; font-weight: 600;'>" + __("Aucun abonnement actif") + "</span>");
						}
						loadReceipts(staffCompany);
					});
				},
			},
			render_input: true,
		});
	}

	// ── Grille informative ────────────────────────────────────────────────────
	// Affichée en haut de la page : prix de chaque offre, offre actuelle surlignée.
	function _renderOffresGrid(currentOffer, regime) {
		var tarifs = _TARIF_JS[regime] || _TARIF_JS["TEE"];
		var html = "<div style=\"display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px;\">";
		_OFFRES_DEF.forEach(function (o, i) {
			var prix = tarifs[i];
			var isCurrent = (o.key === currentOffer);
			var priceStr = prix ? format_number(prix, null, 0) + " FCFA" : __("Sur devis");
			html +=
				"<div style=\"padding:12px 14px;border-radius:10px;border:2px solid " +
				(isCurrent ? o.color : "#e2e8f0") +
				";background:" + (isCurrent ? "#f0f9ff" : "#f8fafc") +
				";position:relative;text-align:left;\">" +
				(isCurrent
					? "<span style=\"position:absolute;top:-9px;left:50%;transform:translateX(-50%);background:" +
					  o.color + ";color:#fff;font-size:10px;font-weight:700;padding:1px 8px;" +
					  "border-radius:99px;white-space:nowrap;\">" + __("Actuelle") + "</span>"
					: "") +
				"<div style=\"font-size:12px;font-weight:700;color:" + o.color + ";margin-bottom:2px;\">" + __(o.key) + "</div>" +
				"<div style=\"font-size:17px;font-weight:800;color:#0f172a;\">" + priceStr + "</div>" +
				"<div style=\"font-size:11px;color:#94a3b8;\">" + __("/mois") + "</div>" +
				"</div>";
		});
		html += "</div>";
		$("#abonnement-offres-grid").html(html).show();
	}
	// ── Fin grille informative ─────────────────────────────────────────────────

	function renderOffreButtons(currentOffer, regime) {
		var tarifs = _TARIF_JS[regime] || _TARIF_JS["TEE"];
		var $btns = $(".abonnement-offres-buttons").empty();
		_OFFRES_DEF.forEach(function (o, i) {
			var prix = tarifs[i];
			if (prix === null || prix === undefined) return; // Sur devis : non affiché
			var isSelected = (o.key === currentOffer);
			$("<button>")
				.addClass("btn abonnement-offre-btn")
				.attr("data-offer", o.key)
				.css({
					padding: "10px 12px",
					"border-radius": "10px",
					"font-weight": isSelected ? "700" : "500",
					border: isSelected ? "2px solid #2563eb" : "1px solid #e2e8f0",
					background: isSelected ? "#eff6ff" : "#f8fafc",
					color: isSelected ? "#1d4ed8" : "#334155",
					cursor: "pointer",
					"font-size": "13px",
					"text-align": "center",
				})
				.html(
					"<div style='font-weight:600;margin-bottom:4px;'>" + frappe.utils.escape_html(o.label) + "</div>" +
					"<div style='font-size:12px;color:" + (isSelected ? "#1d4ed8" : "#64748b") + ";'>" +
						format_number(prix, null, 0) + " FCFA/mois" +
					"</div>"
				)
				.on("click", (function (offerKey, offerPrix) {
					return function () {
						selectedOffer = offerKey;
						renderOffreButtons(selectedOffer, regime);
						$("#abonnement-selected-price").html(
							"Montant : <strong>" + format_number(offerPrix, null, 0) + " FCFA/mois</strong>"
						);
					};
				}(o.key, prix)))
				.appendTo($btns);
		});
		// Afficher le prix de l'offre actuellement sélectionnée
		var selIdx = _OFFRES_DEF.findIndex(function (x) { return x.key === currentOffer; });
		var selPrix = (selIdx >= 0) ? tarifs[selIdx] : tarifs[0];
		if (selPrix) {
			$("#abonnement-selected-price").html(
				"Montant : <strong>" + format_number(selPrix, null, 0) + " FCFA/mois</strong>"
			);
		}
		$("#abonnement-offre-select").show();
	}

	function requestAndRedirect(paymentMethod) {
		if (staffMode && !staffCompany) {
			frappe.msgprint(__("Choisissez d'abord la PME \u00e0 abonner."));
			return;
		}
		showLoading(__("Connexion \u00e0 votre op\u00e9rateur..."));
		frappe.call({
			method: "sitiame_core.subscription_api.get_or_create_pme_checkout_url",
			args: { payment_method: paymentMethod, company: staffCompany, offer: staffMode ? null : selectedOffer },
		}).then(function (r) {
			var res = r.message || {};
			if (res.status === "Pay\u00e9") {
				// a payment still open had gone through: nothing to pay
				showPaid(res);
				return;
			}
			if (res.payment_url) {
				$("#btn-payment-direct").attr("href", res.payment_url);
				showOnly("ready");
				window.location.href = res.payment_url;
			} else {
				showOnly("choose");
				frappe.msgprint(__("Impossible d'obtenir le lien de paiement. Veuillez r\u00e9essayer ou contacter le support SITIAME."));
			}
		}).catch(function () {
			// the server error is already shown by frappe.call: let them retry
			showOnly("choose");
		});
	}
};
