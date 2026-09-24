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
			"<h3 style='font-weight: 700; color: #0f172a; margin-bottom: 6px; font-size: 22px;'>" + __("Abonnement SITIAME CAPITAL") + "</h3>" +
			"<p style='color: #64748b; font-size: 14px; margin-bottom: 25px;'>" + __("Pack Premium Enterprise : <strong>15 000 FCFA</strong> / mois<br><span style='font-size: 13px; color: #94a3b8;'>Mobile Money (Wave, Orange, MTN, Moov) &amp; Cartes bancaires</span>") + "</p>" +

			// State: Loading & Redirecting
			"<div id='abonnement-state-loading' style='padding: 20px 0;'>" +
				"<div class='spinner-border text-primary' role='status' style='width: 3rem; height: 3rem; margin-bottom: 15px;'></div>" +
				"<div style='font-size: 16px; font-weight: 600; color: #1e293b;'>" + __("Connexion au guichet CinetPay...") + "</div>" +
				"<div style='font-size: 13px; color: #94a3b8; margin-top: 6px;'>" + __("Vous allez \u00eatre redirig\u00e9 vers la page de paiement s\u00e9curis\u00e9e.") + "</div>" +
			"</div>" +

			// State: Direct Link Ready
			"<div id='abonnement-state-ready' style='display: none; margin-top: 20px;'>" +
				"<a id='btn-cinetpay-direct' href='#' target='_self' class='btn btn-primary btn-lg' style='padding: 12px 32px; font-size: 15px; font-weight: 600; border-radius: 8px; text-decoration: none; display: inline-block; box-shadow: 0 4px 12px rgba(37,99,235,0.25);'>" +
					__("Acc\u00e9der \u00e0 CinetPay maintenant") +
				"</a>" +
				"<div style='font-size: 12px; color: #94a3b8; margin-top: 12px;'>" + __("Si la redirection automatique ne d\u00e9marre pas, cliquez sur le bouton ci-dessus.") + "</div>" +
			"</div>" +

			// State: Already subscribed (no automatic redirect to CinetPay)
			"<div id='abonnement-state-active' style='display: none; padding: 20px 0;'>" +
				"<div style='font-size: 20px; font-weight: 700; color: #15803d; margin-bottom: 8px;'>" + __("Abonnement actif") + "</div>" +
				"<div id='abonnement-active-desc' style='font-size: 14px; color: #475569; margin-bottom: 25px; line-height: 1.5;'></div>" +
				"<button id='btn-extend-subscription' class='btn btn-primary' style='border-radius: 8px; padding: 11px 24px; font-weight: 600;'>" +
					__("Prolonger d'un mois (15 000 FCFA)") +
				"</button>" +
			"</div>" +

			// State: Success
			"<div id='abonnement-state-success' style='display: none; padding: 20px 0;'>" +
				"<div style='font-size: 52px; color: #16a34a; margin-bottom: 12px;'>\u2705</div>" +
				"<div style='font-size: 20px; font-weight: 700; color: #15803d; margin-bottom: 8px;'>" + __("Paiement valid\u00e9 avec succ\u00e8s !") + "</div>" +
				"<div id='abonnement-success-desc' style='font-size: 14px; color: #475569; margin-bottom: 25px; line-height: 1.5;'>" + __("Votre abonnement Enterprise est actif.") + "</div>" +
				"<button id='btn-return-desk-success' class='btn btn-primary' style='border-radius: 8px; padding: 10px 26px; font-weight: 600;'>" + __("Acc\u00e9der \u00e0 mon espace Desk") + "</button>" +
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

	$("#btn-extend-subscription").on("click", function () {
		$("#abonnement-state-active").hide();
		$("#abonnement-state-loading").show();
		requestAndRedirect(0);
	});

	function endsOnText(sub) {
		if (!sub || !sub.ends_on) return "";
		return __("Actif jusqu'au <strong>{0}</strong>.", [frappe.datetime.str_to_user(sub.ends_on)]);
	}

	$("#btn-retry-payment").on("click", function () {
		$("#abonnement-state-failed").hide();
		$("#abonnement-state-loading").show();
		requestAndRedirect(1);
	});

	var cinetpayStatus = (getQueryParam("cinetpay_status") || "").toLowerCase();
	var returnDocname = getQueryParam("docname");

	if (cinetpayStatus === "failed") {
		$("#abonnement-state-loading").hide();
		$("#abonnement-state-failed").show();
		return;
	}

	if (returnDocname || cinetpayStatus === "success") {
		frappe.call({
			method: "sitiame_core.subscription_api.check_pme_subscription_status",
			args: { docname: returnDocname },
		}).then(function (r) {
			var data = r.message || {};
			if (data.status === "Pay\u00e9") {
				$("#abonnement-state-loading").hide();
				$("#abonnement-state-ready").hide();
				if (data.company) {
					$("#abonnement-success-desc").html(__("Votre abonnement Enterprise est actif pour la soci\u00e9t\u00e9 <strong>{0}</strong>.", [frappe.utils.escape_html(data.company)]) + " " + endsOnText(data.subscription));
				}
				$("#abonnement-state-success").show();
			} else if (data.status === "\u00c9chou\u00e9") {
				$("#abonnement-state-loading").hide();
				$("#abonnement-state-failed").show();
			} else {
				requestAndRedirect(0);
			}
		}).catch(function () {
			requestAndRedirect(0);
		});
	} else {
		frappe.call({
			method: "sitiame_core.subscription_api.get_my_subscription",
		}).then(function (r) {
			var sub = r.message || {};
			if (!sub.company && frappe.user.has_role("System Manager")) {
				$container.hide();
				renderAdminPanel();
			} else if (!sub.company) {
				$("#abonnement-state-loading").hide();
				$("#abonnement-state-error").html(__("Cette page est réservée aux comptes PME : aucune société n'est rattachée à votre compte. Connectez-vous avec le compte de la PME pour payer son abonnement.")).show();
			} else if (sub.active) {
				$("#abonnement-state-loading").hide();
				$("#abonnement-active-desc").html(endsOnText(sub));
				$("#abonnement-state-active").show();
			} else {
				requestAndRedirect(0);
			}
		}).catch(function () {
			requestAndRedirect(0);
		});
	}

	// Sitiame staff: generate a checkout link for any PME (to send it to
	// them) and see every PME's subscription state.
	function renderAdminPanel() {
		var $admin = $(
			"<div style='max-width: 1000px; margin: 24px auto; padding: 0 16px;'>" +
				"<div style='background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); padding: 20px 22px; margin-bottom: 20px;'>" +
					"<h4 style='font-weight: 700; margin: 0 0 4px;'>" + __("Générer un lien de paiement") + "</h4>" +
					"<p style='color: #64748b; font-size: 13px; margin-bottom: 12px;'>" + __("Choisissez la PME, générez le lien CinetPay (15 000 FCFA / 1 mois) et envoyez-le-lui.") + "</p>" +
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
				freeze_message: __("Génération du lien CinetPay..."),
			}).then(function (r) {
				var res = r.message || {};
				if (!res.payment_url) {
					frappe.msgprint(__("CinetPay n'a pas renvoyé de lien. Voir le journal des erreurs."));
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

	function requestAndRedirect(forceNew) {
		frappe.call({
			method: "sitiame_core.subscription_api.get_or_create_pme_checkout_url",
			args: { force_new: forceNew || 0 },
		}).then(function (r) {
			var res = r.message || {};
			if (res.status === "Pay\u00e9") {
				$("#abonnement-state-loading").hide();
				$("#abonnement-state-ready").hide();
				$("#abonnement-state-success").show();
				return;
			}
			var paymentUrl = res.payment_url;
			if (paymentUrl) {
				$("#btn-cinetpay-direct").attr("href", paymentUrl);
				$("#abonnement-state-ready").show();
				window.location.href = paymentUrl;
			} else {
				$("#abonnement-state-loading").hide();
				$("#abonnement-state-error").html(__("Impossible d'obtenir le lien de paiement CinetPay. Veuillez contacter le support SITIAME.")).show();
			}
		}).catch(function (err) {
			$("#abonnement-state-loading").hide();
			var msg = (err && err.message) ? err.message : __("Erreur lors de l'initialisation du paiement CinetPay.");
			$("#abonnement-state-error").html(msg).show();
		});
	}
};
