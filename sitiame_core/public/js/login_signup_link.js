// Adds a "S'inscrire" link to the public login page, pointing to the
// company registration form provided by this app.
(function () {
	function addSignupLink() {
		if (window.location.pathname.indexOf("/login") === -1) return;
		if (document.getElementById("sitiame-signup-link")) return;

		var forgotLink = document.querySelector('a[href*="forgot"], .page-card-actions a');
		var container = document.querySelector(".page-card, .for-login, form");
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
