# Sitiame Core

Application Frappe fournissant une page d'inscription publique pour les entreprises (`/company-signup`), qui cree automatiquement un enregistrement Company et un compte User ERPNext, connecte l'utilisateur et le redirige vers `/app`.

## Installation

```bash
bench get-app https://github.com/YANIXX35/sitiame_core.git
bench --site <votre-site> install-app sitiame_core
```

## Licence

MIT

## Tests

Unit tests for the pure logic (OCR parsing, HT/TVA/TTC, Liasse SYSCOHADA,
CinetPay phone format, receipt parsing). They run without bench or a site,
with a minimal frappe stand-in (`tests/conftest.py`), so production data is
never touched:

```bash
pip install pytest requests
python -m pytest tests -q
```

They also run on GitHub Actions on every push (`.github/workflows/tests.yml`).

## Deployment

Only through `scripts/deploy.sh`, copied on the server as
`/root/sitiame_core_deploy.sh` (see the header of that file). Never
`git pull` by hand inside the containers: the stack runs on a local image
and hand-pulled code is lost when the containers are recreated.
