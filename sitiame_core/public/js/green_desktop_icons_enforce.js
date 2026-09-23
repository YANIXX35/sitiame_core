// green_desktop_icons.css doesn't reach the tiles rendered inside the
// "open folder" popup (#desktop-modal) -- confirmed via live DevTools
// inspection: the .icon-container class is present and matches the CSS
// selector, the stylesheet is loaded (200, fresh), yet no rule from it
// shows up in the Styles panel for that element. Root cause not
// identified (not a specificity/!important issue -- the rule doesn't even
// appear as a candidate), so this enforces the same colors directly via
// inline styles instead of relying on the CSS cascade, which always wins
// regardless of whatever is blocking the stylesheet there.
(function () {
	var GREEN = "#16A34A";
	var GRAYSCALE_FILTER = "grayscale(1) sepia(1) hue-rotate(90deg) saturate(3) brightness(0.95)";

	function paint(container) {
		container.style.setProperty("background-color", GREEN, "important");
		var img = container.querySelector("img.app-icon");
		if (img) img.style.setProperty("filter", GRAYSCALE_FILTER, "important");
		var letter = container.querySelector("svg.desktop-alphabet");
		if (letter) letter.style.setProperty("color", "#FFFFFF", "important");
	}

	function paintAll(root) {
		(root || document).querySelectorAll(".icon-container").forEach(paint);
	}

	var observer = new MutationObserver(function (mutations) {
		mutations.forEach(function (m) {
			m.addedNodes.forEach(function (node) {
				if (node.nodeType !== 1) return;
				if (node.classList && node.classList.contains("icon-container")) paint(node);
				if (node.querySelectorAll) paintAll(node);
			});
		});
	});

	observer.observe(document.body, { childList: true, subtree: true });

	paintAll();
})();
