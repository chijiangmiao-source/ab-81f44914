"""HTTP-level tests for the FastAPI service."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def post(payload):
    return client.post("/api/v1/solve", json=payload)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_info_limits():
    info = client.get("/api/v1/info").json()
    assert info["max_points"] == 40
    assert info["max_channels"] == 160


def test_basic_solve_payload():
    r = post(
        {
            "points": ["A", "B", "C"],
            "root": "A",
            "channels": [
                {"id": "e1", "source": "A", "target": "B", "cost": 3},
                {"id": "e2", "source": "A", "target": "C", "cost": 5},
                {"id": "e3", "source": "B", "target": "C", "cost": 1},
            ],
        }
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["tree"]["total_cost"] == 4
    assert body["tree"]["channel_ids"] == ["e1", "e3"]
    # every non-root point appears exactly once as a target
    targets = sorted(e["target"] for e in body["tree"]["edges"])
    assert targets == ["B", "C"]
    assert body["unreachable"] == []


def test_string_id_ordering_is_code_point_order():
    # ASCII code-point ordering: "10" < "2".  Equal-cost parallel choice for
    # B must resolve to id "10" (lexicographically smaller string).
    r = post(
        {
            "points": ["A", "B"],
            "root": "A",
            "channels": [
                {"id": "2", "source": "A", "target": "B", "cost": 4},
                {"id": "10", "source": "A", "target": "B", "cost": 4},
            ],
        }
    )
    assert r.status_code == 200
    assert r.json()["tree"]["channel_ids"] == ["10"]


def test_unreachable_returns_422_and_points():
    r = post(
        {
            "points": ["A", "B", "C"],
            "root": "A",
            "channels": [
                {"id": "x", "source": "C", "target": "B", "cost": 1},
            ],
        }
    )
    assert r.status_code == 422
    body = r.json()
    assert body["ok"] is False
    assert body["unreachable"] == ["B", "C"]
    assert "unreachable" in body["error"]["message"]


def test_self_loop_rejected():
    r = post(
        {
            "points": ["A", "B"],
            "root": "A",
            "channels": [{"id": "s", "source": "A", "target": "A", "cost": 1}],
        }
    )
    assert r.status_code == 400
    assert "self loop" in r.json()["error"]["message"]


def test_duplicate_points_rejected():
    r = post({"points": ["A", "A"], "root": "A", "channels": []})
    assert r.status_code == 400


def test_duplicate_channel_ids_rejected():
    r = post(
        {
            "points": ["A", "B"],
            "root": "A",
            "channels": [
                {"id": "e", "source": "A", "target": "B", "cost": 1},
                {"id": "e", "source": "A", "target": "B", "cost": 2},
            ],
        }
    )
    assert r.status_code == 400
    assert "duplicate channel id" in r.json()["error"]["message"]


def test_negative_cost_rejected():
    r = post(
        {
            "points": ["A", "B"],
            "root": "A",
            "channels": [{"id": "e", "source": "A", "target": "B", "cost": -1}],
        }
    )
    assert r.status_code == 400


def test_integer_ids_accepted():
    r = post(
        {
            "points": ["A", "B"],
            "root": "A",
            "channels": [{"id": 7, "source": "A", "target": "B", "cost": 0}],
        }
    )
    assert r.status_code == 200
    assert r.json()["tree"]["channel_ids"] == ["7"]


def test_too_many_points_rejected():
    r = post({"points": [f"p{i}" for i in range(41)], "root": "p0", "channels": []})
    assert r.status_code == 400


def test_too_many_channels_rejected():
    chans = [
        {"id": str(i), "source": "p0", "target": "p1", "cost": i}
        for i in range(161)
    ]
    r = post({"points": ["p0", "p1"], "root": "p0", "channels": chans})
    assert r.status_code == 400


def test_invalid_json_body():
    r = client.post("/api/v1/solve", content="{not json", headers={"content-type": "application/json"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_json"


def test_nested_cycle_payload_has_evidence():
    r = post(
        {
            "points": ["R", "a", "b", "c", "d"],
            "root": "R",
            "channels": [
                {"id": "c1", "source": "b", "target": "a", "cost": 1},
                {"id": "c2", "source": "a", "target": "b", "cost": 1},
                {"id": "c3", "source": "d", "target": "a", "cost": 2},
                {"id": "c4", "source": "b", "target": "d", "cost": 2},
                {"id": "c5", "source": "R", "target": "c", "cost": 1},
                {"id": "c6", "source": "c", "target": "d", "cost": 3},
            ],
        }
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tree"]["total_cost"] == 7
    assert body["tree"]["channel_ids"] == ["c2", "c3", "c5", "c6"]
    # two contraction levels and two expansions
    cyc_rounds = [x for x in body["evidence"]["rounds"] if x.get("cycle")]
    assert len(cyc_rounds) == 2
    assert len(body["evidence"]["expansions"]) == 2
    # every expansion names a removed and an added channel that exist
    known = {"c1", "c2", "c3", "c4", "c5", "c6"}
    for e in body["evidence"]["expansions"]:
        assert e["removed_channel_id"] in known
        assert e["added_channel_id"] in known
        assert e["removed_channel_id"] != e["added_channel_id"]
