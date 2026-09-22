// Makes "Gérer le menu" changes apply immediately to an already-open
// session, instead of only at the next login: the server pushes a
// "sitiame_menu_updated" realtime event (scoped to the affected user via
// frappe.publish_realtime(..., user=user)) after saving, and this reloads
// the page so the freshly filtered bootinfo (desktop icons + sidebar
// items) gets picked up right away.
frappe.ready(function () {
	if (!frappe.realtime || !frappe.session || !frappe.session.user || frappe.session.user === "Guest") {
		return;
	}

	frappe.realtime.on("sitiame_menu_updated", function () {
		frappe.show_alert({ message: __("Votre menu a été mis à jour."), indicator: "blue" });
		setTimeout(function () {
			window.location.reload();
		}, 800);
	});
});
