frappe.pages["erp-abonnement"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Abonnement SITIAME"),
		single_column: true,
	});

	var $container = $(
		"<div style='max-width: 600px; margin: 30px auto; padding: 35px 25px; background: #ffffff; border-radius: 14px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); text-align: center; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif;'>" +
			"<div style='font-size: 44px; margin-bottom: 12px;'>\uD83D\uDCB3</div>" +
			"<h3 style='font-weight: 700; color: #0f172a; margin-bottom: 6px; font-size: 22px;'>" + __("Abonnement SITIAME CAPITAL") + "</h3>" +
			"<p style='color: #64748b; font-size: 14px; margin-bottom: 25px;'>" + __("Tarif : <strong>15 000 FCFA</strong> / mois (Mobile Money, Wave, Orange, MTN, Moov, Carte)") + "</p>" +
			"<div id='abonnement-state-loading' style='padding: 20px 0;'>" +
				"<div class='spinner-border text-primary' role='status' style='width: 2.8rem; height: 2.8rem; margin-bottom: 15px;'></div>" +
				"<div style='font-size: 16px; font-weight: 600; color: #1e293b;'>" + __("Ouverture de votre guichet CinetPay...") + "</div>" +
				"<div style='font-size: 13px; color: #94a3b8; margin-top: 6px;'>" + __("Vous allez \u00eatre redirig\u00e9 vers la page de paiement s\u00e9curis\u00e9e.") + "</div>" +
			"</div>" +
			"<div id='abonnement-state-ready' style='display: none; margin-top: 20px;'>" +
				"<a id='btn-cinetpay-direct' href='#' target='_self' class='btn btn-primary btn-lg' style='padding: 12px 30px; font-size: 15px; font-weight: 600; border-radius: 8px; text-decoration: none; display: inline-block;'>" +
					__("Acc\u00e9der directement \u00e0 CinetPay") +
				"</a>" +
				"<div style='font-size: 12px; color: #94a3b8; margin-top: 12px;'>" + __("Si la redirection automatique ne d\u00e9marre pas, cliquez sur le bouton ci-dessus.") + "</div>" +
			"</div>" +
			"<div id='abonnement-state-success' style='display: none; padding: 20px 0;'>" +
				"<div style='font-size: 48px; color: #16a34a; margin-bottom: 10px;'>\u2713</div>" +
				"<div style='font-size: 18px; font-weight: 700; color: #15803d; margin-bottom: 6px;'>" + __("Paiement valid\u00e9 avec succ\u00e8s !") + "</div>" +
				"<div id='abonnement-success-desc' style='font-size: 14px; color: #475569; margin-bottom: 20px;'>" + __("Votre abonnement Enterprise est actif.") + "</div>" +
				"<button id='btn-return-desk' class='btn btn-primary' style='border-radius: 6px; padding: 8px 20px; font-weight: 600;'>" + __("Retour \u00e0 l'accueil") + "</button>" +
			"</div>" +
			"<div id='abonnement-state-error' style='display: none; padding: 15px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; color: #b91c1c; font-size: 14px; margin-top: 15px;'>" +
			"</div>" +
		"</div>"
	).appendTo(page.body);

	$("#btn-return-desk").on("click", function () {
		frappe.set_route("app");
	});

	var urlParams = new URLSearchParams(window.location.search);
	var returnDocname = urlParams.get("docname");

	if (returnDocname) {
		frappe.call({
			method: "sitiame_core.subscription_api.check_pme_subscription_status",
			args: { docname: returnDocname },
		}).then(function (r) {
			var data = r.message || {};
			if (data.status === "Pay\u00e9") {
				$("#abonnement-state-loading").hide();
				$("#abonnement-state-ready").hide();
				if (data.company) {
					$("#abonnement-success-desc").html(__("Votre abonnement Enterprise est actif pour la soci\u00e9t\u00e9 <strong>{0}</strong>.", [frappe.utils.escape_html(data.company)]));
				}
				$("#abonnement-state-success").show();
				return;
			}
			initiateRedirect();
		}).catch(function () {
			initiateRedirect();
		});
	} else {
		initiateRedirect();
	}

	function initiateRedirect() {
		frappe.call({
			method: "sitiame_core.subscription_api.get_or_create_pme_checkout_url",
		}).then(function (r) {
			var res = r.message || {};
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
