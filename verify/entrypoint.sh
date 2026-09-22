#!/usr/bin/env bash
# One-shot verification pipeline. Exits non-zero if ANY stage fails.
#   1. backend unit tests
#   2. backend bytecode "build" + frontend production build (tsc + vite)
#   3. API/HTTP smoke against the real running containers
#   4. scenario cross-checks (nested cycles / parallel channels /
#      lexicographic tie tree / unreachable points) vs an independent
#      brute-force optimum, plus served-page checks
set -uo pipefail

API_URL="${API_URL:-http://api:8000}"
WEB_URL="${WEB_URL:-http://web:8080}"
# Paths default to the in-image layout; overridable for local runs.
BACKEND_DIR="${BACKEND_DIR:-/srv/backend}"
WEB_DIR="${WEB_DIR:-/srv/web}"
VERIFY_DIR="${VERIFY_DIR:-/verify}"

stage() { echo; echo "================ $* ================"; }
rc=0

stage "1/4 backend unit tests (pytest)"
( cd "$BACKEND_DIR" && python -m pytest tests -q ) || rc=1

stage "2/4 builds"
echo "-- backend bytecode compile --"
( cd "$BACKEND_DIR" && python -m compileall -q app ) || rc=1
echo "-- frontend production build (tsc -b && vite build) --"
( cd "$WEB_DIR" && npm run build ) || rc=1

stage "3/4 API / HTTP smoke against real containers"
python - "$API_URL" "$WEB_URL" <<'PY' || rc=1
import json, sys, time, urllib.request, urllib.error
api, web = sys.argv[1], sys.argv[2]

def get(url, tries=30):
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                return r.status, r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.0)
    raise SystemExit(f"never reached {url}: {last}")

s, body = get(api + "/health")
assert s == 200 and json.loads(body)["status"] == "ok", (s, body)
print("smoke GET", api + "/health", "->", s, json.loads(body))

s, body = get(web + "/")
assert s == 200 and b'<!doctype html>' in body.lower(), s
print("smoke GET", web + "/", "->", s, f"({len(body)} bytes)")

# same-origin API proxy exposed by the web container must also answer
s, body = get(web + "/health")
assert s == 200 and json.loads(body)["status"] == "ok", (s, body)
print("smoke GET", web + "/health (proxied)", "->", s)

# minimal real solve through the API
req = urllib.request.Request(
    api + "/api/v1/solve",
    data=json.dumps({
        "points": ["R", "a", "b"],
        "root": "R",
        "channels": [
            {"id": "e1", "source": "R", "target": "a", "cost": 4},
            {"id": "e2", "source": "a", "target": "b", "cost": 1},
            {"id": "e3", "source": "R", "target": "b", "cost": 9},
        ],
    }).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=10) as r:
    payload = json.loads(r.read())
assert payload["ok"] and payload["tree"]["total_cost"] == 5, payload
assert payload["tree"]["channel_ids"] == ["e1", "e2"], payload
print("smoke POST /api/v1/solve -> total 5, ids ['e1','e2']")
PY

stage "4/4 scenario verification against real API + page"
python "$VERIFY_DIR/verify.py" || rc=1

echo
if [ "$rc" -eq 0 ]; then
  echo "VERIFY RESULT: SUCCESS (all stages passed)"
else
  echo "VERIFY RESULT: FAILURE (see stage output above)"
fi
exit "$rc"
