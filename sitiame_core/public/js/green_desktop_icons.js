// Frappe's own desktop tile renderer only knows two background colors --
// "gray" and "blue" -- hardcoded in frappe.utils.desktop_pallete
// (frappe/public/js/frappe/utils/utils.js). Any other value silently
// breaks the tile's background (undefined color). This adds a real
// "green" entry to that palette so tiles can actually use it, matching
// what the user asked: all /desk tiles in the same green as "Frappe HR".
frappe.ready(function () {
	if (frappe.utils && frappe.utils.desktop_pallete) {
		frappe.utils.desktop_pallete.green = "#16A34A";
	}
});
