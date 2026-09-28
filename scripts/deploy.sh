#!/usr/bin/env bash
# Deploy sitiame_core on the production VPS (run as root on the server:
#   bash /root/sitiame_core_deploy.sh
# after copying this file there).
#
# Why this exists: the stack runs on a local image (sitiame/erpnext:current)
# that already contains frappe, erpnext, hrms and sitiame_core. Updating the
# code with a plain `git pull` inside the containers would be lost the next
# time they are recreated, so every deploy bakes the new code into a new
# image and recreates all ERPNext services from it:
#   1. pull sitiame_core in the backend container
#   2. migrate + build assets + clear cache
#   3. commit the backend container as a new dated image, tag it :current
#   4. recreate every ERPNext service from :current
#   5. health check, and keep only the last 3 dated images
set -euo pipefail

# One deploy at a time: two runs started together (2026-09-28) crossed at
# `docker commit` ("snapshot does not exist") and baked a mixed image. A
# second run now waits for the first one (up to 15 min) instead.
exec 9>/var/lock/sitiame_core_deploy.lock
if ! flock -w 900 9; then
	echo "Another deploy has been running for 15 min - aborting." >&2
	exit 1
fi

PROJECT=sitiame-prod
COMPOSE=/root/sitiame-prod-compose.yml
SITE=erp.sitiame-capital.com
BACKEND=${PROJECT}-backend-1
BENCH=/home/frappe/frappe-bench
SERVICES="backend frontend websocket scheduler queue-short queue-long"

echo "== 1. git pull"
# The repository is private (2026-09-28): GitHub is read here on the host
# with a read-only deploy key, then handed to the container as a git
# bundle -- the container has no ssh client and holds no credential.
MIRROR=/root/sitiame_core.git
DEPLOY_KEY=/root/.ssh/sitiame_core_deploy_key
export GIT_SSH_COMMAND="ssh -i $DEPLOY_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
[ -d "$MIRROR" ] || git clone --bare -q git@github.com:YANIXX35/sitiame_core.git "$MIRROR"
git --git-dir="$MIRROR" fetch -q origin +refs/heads/master:refs/heads/master
git --git-dir="$MIRROR" bundle create -q /tmp/sitiame_core.bundle master
docker cp /tmp/sitiame_core.bundle "$BACKEND":/tmp/sitiame_core.bundle
rm -f /tmp/sitiame_core.bundle
docker exec -w "$BENCH/apps/sitiame_core" "$BACKEND" bash -c \
	'm=$(git ls-files -m | grep "\.pyc$" || true); [ -n "$m" ] && git checkout -- $m; git pull --ff-only /tmp/sitiame_core.bundle master'
docker exec -u root "$BACKEND" rm -f /tmp/sitiame_core.bundle
REV=$(docker exec -w "$BENCH/apps/sitiame_core" "$BACKEND" git rev-parse --short HEAD)
echo "   sitiame_core at $REV"

echo "== 2. migrate + build"
docker exec -w "$BENCH" "$BACKEND" bench --site "$SITE" migrate
docker exec -w "$BENCH" "$BACKEND" bench build --app sitiame_core
# hooks.py is cached in Redis ("app_hooks") and migrate does not drop it:
# without this, a new hook (page_renderer, doctype_list_js...) stays
# inactive after deploy (seen 2026-09-28), and 404s cached before the
# deploy keep being served.
docker exec -w "$BENCH" "$BACKEND" bench --site "$SITE" clear-cache

echo "== 3. bake image"
TAG="sitiame/erpnext:$(date -u +%Y%m%d-%H%M)-$REV"
docker commit --pause=false -m "deploy sitiame_core $REV" "$BACKEND" "$TAG" >/dev/null
docker tag "$TAG" sitiame/erpnext:current
echo "   $TAG -> sitiame/erpnext:current"

echo "== 4. recreate services"
docker compose -p "$PROJECT" -f "$COMPOSE" up -d --force-recreate $SERVICES

echo "== 5. health check"
for i in $(seq 1 30); do
	if docker exec -w "$BENCH" "$BACKEND" bench --site "$SITE" execute frappe.ping >/dev/null 2>&1; then
		echo "   site OK"
		break
	fi
	[ "$i" = 30 ] && { echo "   SITE NOT RESPONDING - roll back: docker tag <previous image> sitiame/erpnext:current, then rerun step 4"; exit 1; }
	sleep 5
done
docker exec -w "$BENCH/apps/sitiame_core" "$BACKEND" git log --oneline -1

# keep the 3 most recent dated images (layers shared with :current stay)
docker image ls sitiame/erpnext --format '{{.Tag}}' | grep -E '^[0-9]{8}-' | sort -r | tail -n +4 \
	| xargs -r -I{} docker image rm "sitiame/erpnext:{}" >/dev/null 2>&1 || true
echo "== done ($REV)"
