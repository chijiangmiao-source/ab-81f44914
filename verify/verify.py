#!/usr/bin/env python3
"""End-to-end verification against the REAL running containers.

It does NOT trust the service: for every solvable scenario it independently
enumerates *all* valid root arborescences (brute force, standard library
only), computes the true minimum cost and the lexicographically smallest
ascending channel-id sequence, and compares that with what the live API
returns.  Failure reasons / unreachable points and HTTP 4xx validation
behaviour are checked as well.

It also fetches the built web page and its JS bundle and confirms the page
ships exactly the same scenarios (so network graph and evidence shown in the
browser are driven by the inputs checked here).

Exit code is 0 only if every check passes.
"""

from __future__ import annotations

import itertools
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("API_URL", "http://api:8000").rstrip("/")
WEB = os.environ.get("WEB_URL", "http://web:8080").rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))

FAILURES: list[str] = []
PASSED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        global PASSED
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILURES.append(f"{name}: {detail}")
        print(f"  FAIL  {name} :: {detail}")


def http(method: str, url: str, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def wait_for(url: str, what: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(1.0)
    print(f"  TIMEOUT waiting for {what} at {url}")
    return False


# ---------------------------------------------------------------------------
# Independent brute-force optimum (no shared code with the backend image).
# ---------------------------------------------------------------------------
def brute_force(scn: dict):
    points = scn["points"]
    root = scn["root"]
    idx = {n: i for i, n in enumerate(points)}
    channels = scn["channels"]
    incoming = {v: [] for v in points}
    for ch in channels:
        if ch["target"] != root:
            incoming[ch["target"]].append(ch)
    targets = [v for v in points if v != root]
    if any(not incoming[v] for v in targets):
        return None  # certainly no arborescence
    best = None
    for combo in itertools.product(*(incoming[v] for v in targets)):
        parent = {t: ch["source"] for t, ch in zip(targets, combo)}
        seen = {root}
        changed = True
        while changed:
            changed = False
            for v in targets:
                if v not in seen and parent[v] in seen:
                    seen.add(v)
                    changed = True
        if len(seen) != len(points):
            continue
        cost = sum(ch["cost"] for ch in combo)
        ids = tuple(sorted(ch["id"] for ch in combo))
        cand = (cost, ids)
        if best is None or cand < best:
            best = cand
    return best  # may still be None if nothing reaches some point


def load_scenarios():
    with open(os.path.join(HERE, "scenarios.json"), encoding="utf-8") as f:
        return json.load(f)["scenarios"]


def verify_scenarios(scenarios) -> set[str]:
    solvable_keys = set()
    for scn in scenarios:
        print(f"- scenario '{scn['key']}': {scn['title']}")
        status, body = http("POST", f"{API}/api/v1/solve", _request_of(scn))
        exp = scn["expect"]
        check(f"{scn['key']} status {exp['status']}", status == exp["status"],
              f"got {status}: {body}")

        if status == 200:
            solvable_keys.add(scn["key"])
            # independent optimum
            truth = brute_force(scn)
            check(f"{scn['key']} independently computed optimum exists", truth is not None)
            if truth is not None:
                check(f"{scn['key']} total cost exact minimum",
                      body["tree"]["total_cost"] == truth[0],
                      f"api={body['tree']['total_cost']} brute={truth[0]}")
                ids = body["tree"]["channel_ids"]
                check(f"{scn['key']} tie-break lexicographically minimal",
                      tuple(ids) == truth[1], f"api={ids} brute={list(truth[1])}")
            # canonical-tree invariants
            edges = body["tree"]["edges"]
            non_root = [p for p in scn["points"] if p != scn["root"]]
            check(f"{scn['key']} every non-root point has exactly one incoming edge",
                  sorted(e["target"] for e in edges) == sorted(non_root)
                  and len({e["channel_id"] for e in edges}) == len(edges),
                  f"edges={edges}")
            check(f"{scn['key']} channel ids match edge set",
                  body["tree"]["channel_ids"] == sorted(e["channel_id"] for e in edges))
            check(f"{scn['key']} reported costs are authoritative",
                  all(next(c["cost"] for c in scn["channels"] if c["id"] == e["channel_id"])
                      == e["cost"] for e in edges))
            # reachability from root following selected edges
            fwd = {p: [] for p in scn["points"]}
            for e in edges:
                fwd[e["source"]].append(e["target"])
            seen, stack = {scn["root"]}, [scn["root"]]
            while stack:
                u = stack.pop()
                for v in fwd[u]:
                    if v not in seen:
                        seen.add(v)
                        stack.append(v)
            check(f"{scn['key']} tree reaches every point from root",
                  seen == set(scn["points"]), f"reached={sorted(seen)}")
            # evidence records
            rounds = body["evidence"]["rounds"]
            expansions = body["evidence"]["expansions"]
            check(f"{scn['key']} contraction rounds = {exp['contractions']}",
                  len([r for r in rounds if r.get("contraction")]) == exp["contractions"],
                  f"rounds={[r.get('contraction') for r in rounds]}")
            check(f"{scn['key']} expansions = {exp['expansions']}",
                  len(expansions) == exp["expansions"], f"got {len(expansions)}")
            if exp["contractions"]:
                # each expansion swap must be a real remove/add channel pair
                known = {c["id"] for c in scn["channels"]}
                ok_swaps = all(
                    e["removed_channel_id"] in known and e["added_channel_id"] in known
                    and e["removed_channel_id"] != e["added_channel_id"]
                    for e in expansions
                )
                check(f"{scn['key']} expansion swaps are concrete channel replacements",
                      ok_swaps)
                # audit: replay the swaps against the final edge list
                final_ids = set(body["tree"]["channel_ids"])
                check(f"{scn['key']} every added channel is in the canonical tree",
                      all(e["added_channel_id"] in final_ids for e in expansions))
                check(f"{scn['key']} no removed channel survives in the tree",
                      all(e["removed_channel_id"] not in final_ids for e in expansions))
            check(f"{scn['key']} perturbed objective decodes back to true cost",
                  int(body["evidence"]["perturbation"]["true_cost"]) == body["tree"]["total_cost"])
        else:
            check(f"{scn['key']} unreachable points reported",
                  sorted(body.get("unreachable", [])) == sorted(exp["unreachable"]),
                  f"got {body.get('unreachable')}")
            check(f"{scn['key']} explicit reason present",
                  bool(body.get("error", {}).get("message")))
            check(f"{scn['key']} brute force agrees the instance is infeasible",
                  brute_force(scn) is None)
    return solvable_keys


def _request_of(scn: dict) -> dict:
    return {"points": scn["points"], "root": scn["root"], "channels": scn["channels"]}


def verify_validation():
    print("- input validation via the real API")
    base = {"points": ["A", "B"], "root": "A"}
    cases = [
        ("self loop forbidden",
         {**base, "channels": [{"id": "s", "source": "A", "target": "A", "cost": 1}]}, 400),
        ("duplicate channel id",
         {**base, "channels": [
             {"id": "e", "source": "A", "target": "B", "cost": 1},
             {"id": "e", "source": "A", "target": "B", "cost": 2}]}, 400),
        ("negative cost",
         {**base, "channels": [{"id": "e", "source": "A", "target": "B", "cost": -3}]}, 400),
        ("duplicate points",
         {"points": ["A", "A"], "root": "A", "channels": []}, 400),
        ("too few points",
         {"points": ["A"], "root": "A", "channels": []}, 400),
        ("unknown root",
         {"points": ["A", "B"], "root": "Z", "channels": []}, 400),
    ]
    for name, payload, want in cases:
        status, body = http("POST", f"{API}/api/v1/solve", payload)
        check(name, status == want and body.get("ok") is False
              and bool(body.get("error", {}).get("message")),
              f"status={status} body={body}")

    # parallel channels must be accepted
    status, body = http("POST", f"{API}/api/v1/solve", {
        "points": ["A", "B"], "root": "A",
        "channels": [
            {"id": "a", "source": "A", "target": "B", "cost": 5},
            {"id": "b", "source": "A", "target": "B", "cost": 5},
        ]})
    check("parallel channels accepted and tie resolved by id",
          status == 200 and body["tree"]["channel_ids"] == ["a"],
          f"status={status} body={body}")


def fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.read().decode()


def verify_web(scenarios):
    print("- built web page")
    html = fetch(f"{WEB}/")
    check("index.html served",
          "<!doctype html>" in html.lower() and '<div id="root"' in html
          and re.search(r'<script[^>]+src="[^"]+\.js"', html) is not None,
          html[:200])
    m = re.search(r'<script[^>]+src="([^"]+\.js)"', html)
    check("js bundle referenced", m is not None, html[:200])
    if not m:
        return
    bundle = fetch(f"{WEB}/{m.group(1).lstrip('/')}")
    check("bundle is non-trivial JS", len(bundle) > 20000, f"len={len(bundle)}")
    check("bundle calls the real solve endpoint", "/api/v1/solve" in bundle)
    # The page must embed the exact same scenarios checked against the API.
    for scn in scenarios:
        for ch_id in {c["id"] for c in scn["channels"]}:
            check(f"page bundle ships scenario {scn['key']} channel {ch_id}",
                  json.dumps(ch_id) in bundle or f'"{ch_id}"' in bundle,
                  "scenario missing from built page")
    # evidence/linkage UI strings are present
    for token in ["收缩", "展开", "不可达", "注入根"]:
        check(f"page bundle contains UI text {token}", token in bundle)


def main() -> int:
    print(f"== verify real services: API={API} WEB={WEB} ==")
    api_ok = wait_for(f"{API}/health", "API /health")
    web_ok = wait_for(f"{WEB}/", "web /")
    check("API /health 200 {status:ok}",
          api_ok and json.loads(fetch(f"{API}/health"))["status"] == "ok")
    check("web / reachable", web_ok)
    if not (api_ok and web_ok):
        return 1

    scenarios = load_scenarios()
    verify_scenarios(scenarios)
    verify_validation()
    verify_web(scenarios)

    print()
    print(f"passed: {PASSED}, failed: {len(FAILURES)}")
    if FAILURES:
        print("FAILURES:")
        for f in FAILURES:
            print(" -", f)
        return 1
    print("ALL VERIFICATION CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
