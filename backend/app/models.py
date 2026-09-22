"""Request validation and translation between the JSON API and the solver."""

from __future__ import annotations

import string
from dataclasses import dataclass

from .arboreal import Channel

# Protocol limits fixed by the problem statement.
MIN_POINTS = 2
MAX_POINTS = 40
MAX_CHANNELS = 160
MAX_LABEL_LEN = 16

_PRINTABLE = set(string.printable) - set(string.whitespace)


class ValidationError(Exception):
    def __init__(self, message: str, code: str = "invalid_input", field: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field


@dataclass(frozen=True)
class ParsedRequest:
    point_names: list[str]          # index -> user label
    root_index: int
    root_name: str
    # channels already ranked: cid 1..m follows ascending user channel id
    channel_ids_sorted: list[str]
    channels: list[Channel]


def _check_point_label(label: object) -> str:
    if not isinstance(label, str) or not label:
        raise ValidationError("each point must be a non-empty ASCII string", field="points")
    if len(label) > MAX_LABEL_LEN:
        raise ValidationError(
            f"point label {label!r} exceeds {MAX_LABEL_LEN} characters", field="points"
        )
    if any(ch not in _PRINTABLE for ch in label):
        raise ValidationError(
            f"point label {label!r} contains non-printable or non-ASCII characters",
            field="points",
        )
    return label


def _check_channel_id(cid: object) -> str:
    if isinstance(cid, int) and not isinstance(cid, bool):
        cid = str(cid)
    if not isinstance(cid, str) or not cid:
        raise ValidationError(
            "each channel id must be a non-empty ASCII string (integers are accepted)",
            field="channels.id",
        )
    if len(cid) > MAX_LABEL_LEN:
        raise ValidationError(
            f"channel id {cid!r} exceeds {MAX_LABEL_LEN} characters",
            field="channels.id",
        )
    if any(ch not in _PRINTABLE for ch in cid):
        raise ValidationError(
            f"channel id {cid!r} contains non-printable or non-ASCII characters",
            field="channels.id",
        )
    return cid


def parse_request(payload: dict) -> ParsedRequest:
    """Validate a decoded JSON request body and translate it for the solver."""
    if not isinstance(payload, dict):
        raise ValidationError("request body must be a JSON object")

    raw_points = payload.get("points")
    if not isinstance(raw_points, list):
        raise ValidationError("'points' must be a list", field="points")
    if not (MIN_POINTS <= len(raw_points) <= MAX_POINTS):
        raise ValidationError(
            f"'points' must contain between {MIN_POINTS} and {MAX_POINTS} unique points "
            f"(got {len(raw_points) if isinstance(raw_points, list) else 'non-list'})",
            field="points",
        )

    names = [_check_point_label(p) for p in raw_points]
    if len(set(names)) != len(names):
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise ValidationError(
            f"point labels must be unique; duplicates: {dupes}", field="points"
        )
    index = {name: i for i, name in enumerate(names)}

    root = payload.get("root")
    if not isinstance(root, str):
        raise ValidationError("'root' must be the label of one of the points", field="root")
    if root not in index:
        raise ValidationError(
            f"root {root!r} is not among the supplied points", field="root"
        )

    raw_channels = payload.get("channels", [])
    if not isinstance(raw_channels, list):
        raise ValidationError("'channels' must be a list", field="channels")
    if len(raw_channels) > MAX_CHANNELS:
        raise ValidationError(
            f"at most {MAX_CHANNELS} channels are allowed (got {len(raw_channels)})",
            field="channels",
        )

    seen_ids: set[str] = set()
    parsed_rows = []
    for pos, row in enumerate(raw_channels):
        where = f"channels[{pos}]"
        if not isinstance(row, dict):
            raise ValidationError(f"{where} must be an object", field=where)
        cid = _check_channel_id(row.get("id"))
        if cid in seen_ids:
            raise ValidationError(f"duplicate channel id {cid!r}", field=f"{where}.id")
        seen_ids.add(cid)

        src = row.get("source")
        dst = row.get("target")
        if not isinstance(src, str) or src not in index:
            raise ValidationError(
                f"{where}: source {src!r} is not one of the points", field=f"{where}.source"
            )
        if not isinstance(dst, str) or dst not in index:
            raise ValidationError(
                f"{where}: target {dst!r} is not one of the points", field=f"{where}.target"
            )
        if src == dst:
            raise ValidationError(
                f"{where} (id={cid!r}): self loops are forbidden ({src} -> {src})",
                field=f"{where}.target",
            )

        cost = row.get("cost")
        if isinstance(cost, bool) or not isinstance(cost, int):
            raise ValidationError(
                f"{where} (id={cid!r}): cost must be a non-negative integer",
                field=f"{where}.cost",
            )
        if cost < 0:
            raise ValidationError(
                f"{where} (id={cid!r}): cost must be non-negative (got {cost})",
                field=f"{where}.cost",
            )
        parsed_rows.append((cid, index[src], index[dst], cost))

    # Internal rank cid=1 is the smallest user supplied channel id.  Order is
    # ASCII code-point order of the stringified id.
    ordered = sorted(parsed_rows, key=lambda r: r[0])
    channel_ids_sorted = [r[0] for r in ordered]
    m = len(ordered)
    scale = 1 << m
    channels = [
        Channel(
            cid=i + 1,
            src=s,
            dst=d,
            cost=c,
            w=c * scale - (1 << (m - (i + 1))),
        )
        for i, (_, s, d, c) in enumerate(ordered)
    ]

    return ParsedRequest(
        point_names=names,
        root_index=index[root],
        root_name=root,
        channel_ids_sorted=channel_ids_sorted,
        channels=channels,
    )
