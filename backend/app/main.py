"""FastAPI application: glacier channel arborescence service."""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .arboreal import NoArborescenceError, Round, solve_arborescence
from .models import ValidationError, parse_request

app = FastAPI(
    title="Glacier Confluence Tree API",
    version="1.0.0",
    description="Minimum-cost directed arborescence with auditable contractions.",
)

_cors = os.getenv("CORS_ORIGINS", "*").strip()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors.split(",")] if _cors != "*" else ["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _node_label(idx: int, n_original: int, point_names: list[str]) -> str:
    """Original nodes use point names; contracted super-nodes are K<idx>."""
    if idx < n_original:
        return point_names[idx]
    return f"K{idx}"


def _serialise_rounds(result, point_names: list[str]) -> list[dict]:
    n = len(point_names)
    out = []
    for rnd in result.rounds:
        choices = [
            {
                "target": _node_label(c["target_supernode"], n, point_names),
                "source": _node_label(c["source_supernode"], n, point_names),
                "channel_id": _cid_label(result, c["channel_cid"]),
                "reduced_cost_part": c["weight_cost_part"],
                "perturbed_weight": str(c["weight"]),
            }
            for c in rnd.choices
        ]
        item = {"depth": rnd.depth, "choices": choices}
        if rnd.cycle:
            item["cycle"] = {
                "nodes": [_node_label(v, n, point_names) for v in rnd.cycle["nodes"]],
                "channel_ids": [
                    _cid_label(result, c) for c in rnd.cycle["channel_cids"]
                ],
                "follow": [
                    {
                        "from": _node_label(f["from"], n, point_names),
                        "to": _node_label(f["to"], n, point_names),
                        "channel_id": _cid_label(result, f["channel_cid"]),
                    }
                    for f in rnd.cycle["follow"]
                ],
                "cycle_cost": rnd.cycle["cycle_cost"],
            }
        if rnd.contraction:
            ct = rnd.contraction
            item["contraction"] = {
                "supernode": _node_label(ct["new_supernode"], n, point_names),
                "cycle_nodes": [
                    _node_label(v, n, point_names) for v in ct["cycle_nodes"]
                ],
                "original_points": [
                    point_names[i] for i in ct["original_nodes"]
                ],
                "cycle_channel_ids": [
                    _cid_label(result, c) for c in ct["cycle_channel_cids"]
                ],
                "cycle_cost": ct["cycle_cost"],
            }
        out.append(item)
    return out


def _cid_label(result, cid: int) -> str:
    return result.id_labels[cid - 1]


def _serialise_expansions(result, point_names: list[str]) -> list[dict]:
    n = len(point_names)
    return [
        {
            "depth": e.depth,
            "supernode": _node_label(e.supernode, n, point_names),
            "cycle_nodes": [_node_label(v, n, point_names) for v in e.cycle_nodes],
            "removed_channel_id": _cid_label(result, e.removed_cid),
            "added_channel_id": _cid_label(result, e.added_cid),
            "entered_point": _node_label(e.entered_node, n, point_names),
            "external_source": _node_label(e.external_source, n, point_names),
        }
        for e in result.expansions
    ]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "arboreal-api"}


@app.get("/api/v1/info")
def info() -> dict:
    from .models import MAX_CHANNELS, MAX_POINTS, MIN_POINTS

    return {
        "min_points": MIN_POINTS,
        "max_points": MAX_POINTS,
        "max_channels": MAX_CHANNELS,
        "cost": "non-negative integer",
        "tie_break": "lexicographically smallest ascending channel-id sequence",
    }


@app.post("/api/v1/solve")
async def solve(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": {"code": "invalid_json", "message": "request body is not valid JSON"},
                "unreachable": [],
            },
        )

    try:
        parsed = parse_request(payload)
    except ValidationError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "field": exc.field,
                },
                "unreachable": [],
            },
        )

    try:
        result = solve_arborescence(
            n=len(parsed.point_names),
            root=parsed.root_index,
            channels=parsed.channels,
        )
    except NoArborescenceError as exc:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "error": {"code": "no_arborescence", "message": exc.reason},
                "unreachable": [parsed.point_names[i] for i in exc.unreachable],
            },
        )

    # Attach user-facing channel labels ordered by internal cid rank.
    result.id_labels = parsed.channel_ids_sorted  # type: ignore[attr-defined]
    point_names = parsed.point_names

    edges = []
    for cid in result.selected:
        ch = result.channels[cid - 1]
        edges.append(
            {
                "channel_id": _cid_label(result, cid),
                "source": point_names[ch.src],
                "target": point_names[ch.dst],
                "cost": ch.cost,
            }
        )
    edges.sort(key=lambda e: e["channel_id"])

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "points": point_names,
            "root": parsed.root_name,
            "tree": {
                "total_cost": result.total_cost,
                "channel_ids": [e["channel_id"] for e in edges],
                "edges": edges,
            },
            "evidence": {
                "perturbation": {
                    "encoding": "w(e) = cost(e) * 2^m - 2^(m-rank(e)); rank 1 is the "
                    "smallest channel id",
                    "scale": str(result.scale),
                    "perturbed_total": str(result.perturbed_total),
                    "true_cost": result.total_cost,
                    "selected_bit_vector": str(
                        result.total_cost * result.scale - result.perturbed_total
                    ),
                    "bit_vector_reads_as": "bit (m-rank) is set exactly when that channel "
                    "is selected; maximising it = lexicographically smallest ascending "
                    "channel-id sequence",
                    "rule": "among equal-cost trees, minimise the ascending channel-id "
                    "sequence lexicographically",
                },
                "rounds": _serialise_rounds(result, point_names),
                "expansions": _serialise_expansions(result, point_names),
            },
            "unreachable": [],
        },
    )
