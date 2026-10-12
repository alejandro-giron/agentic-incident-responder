#!/usr/bin/env bash
# End-to-end check (usage: scripts/e2e.sh [scenario-id...]):
# for each scenario, inject -> observe symptoms -> heal -> shop healthy again.
# "Healthy" means the home page returns 200 AND a full add-to-cart + checkout succeeds.
set -uo pipefail
cd "$(dirname "$0")/.."
export KUBECONFIG=$PWD/.chaos/kubeconfig
URL=http://localhost:${CHAOS_HTTP_PORT:-8080}
JAR=$(mktemp); trap 'rm -f "$JAR"' EXIT

home() { curl -s -o /dev/null -m 15 -w '%{http_code} %{time_total}s' "$URL/"; }

# Prints "ok <time>" or "fail <http code> <time>".
checkout() {
  rm -f "$JAR"
  curl -s -o /dev/null -m 15 -c "$JAR" -b "$JAR" "$URL/"
  curl -s -o /dev/null -m 15 -c "$JAR" -b "$JAR" -d product_id=OLJCESPC7Z -d quantity=1 "$URL/cart"
  local out
  out=$(curl -s -m 30 -c "$JAR" -b "$JAR" -w '\n%{http_code} %{time_total}s' \
    -d email=someone@example.com -d street_address='1600 Amphitheatre Parkway' -d zip_code=94043 \
    -d city='Mountain View' -d state=CA -d country='United States' -d credit_card_number=4432801561520454 \
    -d credit_card_expiration_month=1 -d credit_card_expiration_year=2039 -d credit_card_cvv=672 \
    "$URL/cart/checkout")
  if grep -q 'Your order is complete' <<<"$out"; then echo "ok $(tail -1 <<<"$out" | cut -d' ' -f2)"; else echo "fail $(tail -1 <<<"$out")"; fi
}

healthy() { [[ $(home) == 200* && $(checkout) == ok* ]]; }

wait_healthy() {
  for _ in $(seq 1 30); do healthy && return 0; sleep 3; done
  return 1
}

make --no-print-directory -s deploy >/dev/null 2>&1 || { echo "deploy failed"; exit 1; }
wait_healthy || { echo "baseline not healthy"; exit 1; }
echo "baseline: home $(home), checkout $(checkout)"

fail=0
for id in ${@:-$(make --no-print-directory -s list)}; do
  echo "== $id"
  make --no-print-directory -s inject SCENARIO="$id" >/dev/null || { echo "  inject FAILED"; fail=1; continue; }
  sleep "${E2E_SETTLE:-45}"
  echo "  home: $(home)  checkout: $(checkout)"
  kubectl get pods --no-headers | awk '{split($2, r, "/")} r[1] != r[2] || $3 != "Running" {print "  pod: "$1" "$2" "$3}'
  make --no-print-directory -s heal >/dev/null || { echo "  heal FAILED"; fail=1; continue; }
  if wait_healthy; then echo "  healed"; else echo "  NOT healthy 90s after heal: home $(home), checkout $(checkout)"; fail=1; fi
done
exit $fail
