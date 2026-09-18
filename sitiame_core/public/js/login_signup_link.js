// Adds a "S'inscrire" link to the public login page, pointing to the
// company registration form provided by this app.
(function () {
	// The logo lives at /files/sitiame-capital-logo.png (Website Settings ->
	// App Logo), but that path silently fails to load for at least one user
	// -- zero network request even attempted, in private browsing too, so
	// some browser/security-extension heuristic is almost certainly
	// blocking "/files/*.png" as a generic "user-uploaded file" pattern.
	// Re-pointing the <img> at our own bundled copy under /assets/ sidesteps
	// that without touching the global Website Settings logo.
	function fixLogoSrc() {
		document.querySelectorAll("img.app-logo").forEach(function (img) {
			if (img.src.indexOf("/files/sitiame-capital-logo.png") !== -1) {
				img.src = "/assets/sitiame_core/images/sitiame-capital-logo.png";
			}
		});
	}

	function addSignupLink() {
		fixLogoSrc();
		if (window.location.pathname.indexOf("/company-signup") !== -1) return;
		if (document.getElementById("sitiame-signup-link")) return;

		// Don't rely on the URL path: the login form can render at "/",
		// "/login", or after a "?redirect-to=" bounce, all with the same DOM.
		var passwordField = document.querySelector('input[type="password"]');
		if (!passwordField) return;

		var container = document.querySelector(".page-card, .for-login") || passwordField.closest("form");
		if (!container) return;

		var p = document.createElement("p");
		p.id = "sitiame-signup-link";
		p.style.textAlign = "center";
		p.style.marginTop = "1rem";
		p.innerHTML = 'Pas encore de compte ? <a href="/company-signup">Inscrire votre entreprise</a>';
		container.parentNode.insertBefore(p, container.nextSibling);
	}

	document.addEventListener("DOMContentLoaded", addSignupLink);
	setTimeout(addSignupLink, 500);
	setTimeout(addSignupLink, 1500);
})();
