frappe.pages["erp-backups"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Sauvegardes"),
		single_column: true,
	});

	page.set_primary_action(__("Lancer une sauvegarde maintenant"), function () {
		frappe.dom.freeze(__("Sauvegarde en cours..."));
		frappe
			.call({ method: "sitiame_core.api.run_erp_backup_now" })
			.then(function () {
				frappe.dom.unfreeze();
				frappe.show_alert({ message: __("Sauvegarde creee."), indicator: "green" });
				render();
			})
			.catch(function () {
				frappe.dom.unfreeze();
			});
	}, "refresh");

	var $intro = $(
		"<p class='text-muted' style='padding:0 15px;'>" +
			__("Une sauvegarde automatique de la base ERPNext est creee toutes les 4 heures. Les 60 dernieres sont conservees (environ 10 jours d'historique).") +
			"</p>"
	).appendTo(page.body);

	var $body = $("<div class='erp-backups-list' style='padding:0 15px;'></div>").appendTo(page.body);

	function render() {
		$body.html("<p class='text-muted'>" + __("Chargement...") + "</p>");
		frappe.call({ method: "sitiame_core.api.list_erp_backups" }).then(function (r) {
			var rows = r.message || [];

			if (!rows.length) {
				$body.html("<p class='text-muted'>" + __("Aucune sauvegarde pour le moment.") + "</p>");
				return;
			}

			var $table = $(
				"<table class='table table-bordered'><thead><tr>" +
					"<th>" + __("Fichier") + "</th>" +
					"<th>" + __("Taille") + "</th>" +
					"<th>" + __("Date") + "</th>" +
					"<th></th>" +
					"</tr></thead><tbody></tbody></table>"
			);
			var $tbody = $table.find("tbody");

			rows.forEach(function (row) {
				var downloadUrl =
					"/api/method/sitiame_core.api.download_erp_backup?filename=" + encodeURIComponent(row.filename);
				var $tr = $(
					"<tr>" +
						"<td>" + frappe.utils.escape_html(row.filename) + "</td>" +
						"<td>" + row.size_mb + " Mo</td>" +
						"<td>" + row.created_at + "</td>" +
						"<td>" +
						"<a class='btn btn-xs btn-default' href='" + downloadUrl + "'>" + __("Telecharger") + "</a> " +
						"<button class='btn btn-xs btn-danger erp-backup-delete'>" + __("Supprimer") + "</button>" +
						"</td>" +
						"</tr>"
				);
				$tr.find(".erp-backup-delete").on("click", function () {
					frappe.confirm(__("Supprimer cette sauvegarde ?"), function () {
						frappe
							.call({
								method: "sitiame_core.api.delete_erp_backup",
								args: { filename: row.filename },
							})
							.then(render);
					});
				});
				$tbody.append($tr);
			});

			$body.empty().append($table);
		});
	}

	render();
};
