"""Minimum-cost directed arborescence (rooted spanning tree) solver.

Implements the Chu-Liu / Edmonds (CLE) algorithm from scratch: no graph
optimisation library is used anywhere.  The input is a directed multigraph
(parallel channels between the same ordered pair of points are allowed)
with non-negative integer costs and a distinguished root.

Tie breaking
------------
When several arborescences share the exact minimum *integer* cost, the
answer must be the one whose list of selected channel identifiers, sorted
ascending, is lexicographically smallest.

This is implemented deterministically with arbitrary-precision integers and
no floats.  With ``m`` channels whose internal ranks are ``cid = 1..m``
(rank 1 = smallest user supplied identifier) and ``SCALE = 2**m``, every
channel gets the perturbed weight::

    w(e) = cost(e) * SCALE - 2 ** (m - cid(e))

and the algorithm *minimises* the sum:

* ``SCALE`` is larger than every possible magnitude of the bit part
  (``<= 2**m - 1``), so a tree with smaller true cost always beats one with
  larger true cost - the primary objective is exactly the integer cost.
* Among equal-cost trees, minimising the negated bit part is the same as
  *maximising* the bit part: a binary number whose bit ``m - cid`` is set
  iff channel ``cid`` is selected.  Channel ids are unique, so every bit is
  0/1 with no carries; the highest set bit decides, and the highest bit is
  the smallest id.  The tree that includes the smallest possible id wins,
  then among those the next smallest, etc. - exactly a lexicographic
  comparison of the two sorted selected-id lists.

CLE's reduced weights are formed by plain subtraction of these perturbed
weights, which are arbitrary (possibly negative) additive edge weights, so
the same ordering is maintained through every contraction; the standard
correctness proof applies to arbitrary additive weights.

Every recursive contraction and every expansion replacement is recorded so
the whole computation can be re-computed / audited.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Channel:
    """A directed channel (multiedge).

    ``cid`` is the unique positive internal rank (1 = smallest user id),
    used both for the lexicographic tie break and for records.  ``w`` is the
    current (possibly reduced) perturbed weight used by the algorithm; the
    original non-negative integer cost is kept in ``cost``.
    """

    cid: int
    src: int
    dst: int
    cost: int
    w: int


@dataclass
class Round:
    """One recursive reduction round of the Chu-Liu/Edmonds algorithm."""

    depth: int
    choices: list[dict] = field(default_factory=list)
    cycle: Optional[dict] = None
    contraction: Optional[dict] = None


@dataclass
class Expansion:
    """One un-contraction step on the way back up from the recursion."""

    depth: int
    supernode: int
    cycle_nodes: list[int]
    removed_cid: int
    added_cid: int
    entered_node: int
    external_source: int


class NoArborescenceError(Exception):
    """Raised when some node cannot be reached from the root."""

    def __init__(self, unreachable: list[int], reason: str):
        self.unreachable = unreachable
        self.reason = reason
        super().__init__(reason)


@dataclass
class ArborescenceResult:
    channels: list[Channel]
    selected: list[int]
    total_cost: int
    perturbed_total: int
    scale: int
    rounds: list[Round]
    expansions: list[Expansion]


def _find_cycle(chosen: dict[int, int], root: int) -> Optional[list[int]]:
    """Return one directed cycle in the functional graph ``chosen``.

    ``chosen[v]`` is the source node of the chosen edge entering ``v``.
    Nodes are iterated in ascending order so records are deterministic.
    """
    for start in sorted(chosen):
        if start == root:
            continue
        seen_pos: dict[int, int] = {}
        path: list[int] = []
        cur = start
        while cur in chosen and cur != root:
            if cur in seen_pos:
                return path[seen_pos[cur]:]
            seen_pos[cur] = len(path)
            path.append(cur)
            cur = chosen[cur]
    return None


def _reachable_from(root: int, adj: dict[int, list[int]]) -> set[int]:
    seen = {root}
    stack = [root]
    while stack:
        u = stack.pop()
        for v in adj[u]:
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def solve_arborescence(
    n: int, root: int, channels: list[Channel]
) -> ArborescenceResult:
    """Compute the minimum-cost root arborescence of a directed multigraph.

    Parameters
    ----------
    n:
        Number of nodes, internally labelled ``0 .. n-1``.
    root:
        Root node; no incoming edge may be selected for it.
    channels:
        Directed channels with unique positive ``cid`` in ``1..m``.  Their
        ``w`` fields are the *original* perturbed weights; reduced weights
        are created on fresh channel objects during contraction.

    Raises
    ------
    NoArborescenceError
        If some node is not reachable from ``root``.
    """
    m = len(channels)
    scale = 1 << m

    # Up-front reachability on the original graph.  Contracting cycles can
    # never create reachability, so anything unreachable here stays
    # unreachable: fail fast with the exact offending points.
    adj: dict[int, list[int]] = {v: [] for v in range(n)}
    for c in channels:
        adj[c.src].append(c.dst)
    reachable = _reachable_from(root, adj)
    missing = sorted(v for v in range(n) if v not in reachable)
    if missing:
        raise NoArborescenceError(
            missing, "unreachable: these points cannot be reached from the root"
        )

    # Original node 0..n-1; super-nodes are allocated n, n+1, ...
    members: dict[int, list[int]] = {v: [v] for v in range(n)}
    rounds: list[Round] = []
    expansions: list[Expansion] = []

    def next_supernode() -> int:
        return max(members) + 1

    def flatten(seq: list[int]) -> list[int]:
        out: list[int] = []
        for s in seq:
            out.extend(members[s])
        return sorted(out)

    def cle(
        nodes: frozenset[int],
        rt: int,
        edges: tuple[Channel, ...],
        depth: int,
    ) -> dict[int, int]:
        """One CLE reduction level.  Returns ``node -> incoming cid``.

        Returned cids always refer to channel objects of the *parent* level
        (cids are preserved when edges are rewritten during contraction), so
        the top-level result refers to original channels.
        """
        rec = Round(depth=depth)

        # 1) cheapest perturbed incoming edge for every non-root node ------
        best_in: dict[int, Channel] = {}
        for e in edges:
            if e.dst == rt:
                continue
            cur = best_in.get(e.dst)
            if cur is None or e.w < cur.w or (e.w == cur.w and e.cid < cur.cid):
                best_in[e.dst] = e

        lacking = sorted(v for v in nodes if v != rt and v not in best_in)
        if lacking:
            # Covered by the up-front reachability check, kept defensive.
            raise NoArborescenceError(
                flatten(lacking),
                "no incoming channel for a contracted node during reduction",
            )

        chosen_src: dict[int, int] = {}
        for v in sorted(best_in):
            e = best_in[v]
            chosen_src[v] = e.src
            rec.choices.append(
                {
                    "target_supernode": v,
                    "source_supernode": e.src,
                    "channel_cid": e.cid,
                    "weight_cost_part": e.cost,
                    "weight": e.w,
                }
            )

        # 2) detect a directed cycle among the chosen edges ----------------
        cyc = _find_cycle(chosen_src, rt)
        if cyc is None:
            # Base case: cheapest incoming edges already form an arborescence.
            rounds.append(rec)
            return {v: best_in[v].cid for v in best_in}

        cyc_set = set(cyc)
        cycle_cids = [best_in[v].cid for v in cyc]
        cycle_cost = sum(best_in[v].cost for v in cyc)
        rec.cycle = {
            "nodes": list(cyc),
            "channel_cids": cycle_cids,
            "cycle_cost": cycle_cost,
            "follow": [
                {"from": chosen_src[v], "to": v, "channel_cid": best_in[v].cid}
                for v in cyc
            ],
        }

        # 3) contract the cycle into one super-node ------------------------
        new_node = next_supernode()
        original_members = flatten(cyc)
        members[new_node] = original_members
        rec.contraction = {
            "new_supernode": new_node,
            "cycle_nodes": list(cyc),
            "original_nodes": original_members,
            "cycle_channel_cids": cycle_cids,
            "cycle_cost": cycle_cost,
        }
        rounds.append(rec)

        contracted: list[Channel] = []
        for e in edges:
            s_in = e.src in cyc_set
            d_in = e.dst in cyc_set
            if s_in and d_in:
                continue  # cycle-internal channels disappear
            if not s_in and not d_in:
                contracted.append(e)
            elif d_in:
                # external -> cycle: CLE reduced weight, cid preserved.
                internal = best_in[e.dst]
                contracted.append(
                    Channel(
                        cid=e.cid,
                        src=e.src,
                        dst=new_node,
                        cost=e.cost - internal.cost,
                        w=e.w - internal.w,
                    )
                )
            else:
                # cycle -> external: re-anchor on the super-node.
                contracted.append(
                    Channel(cid=e.cid, src=new_node, dst=e.dst, cost=e.cost, w=e.w)
                )

        new_nodes = frozenset((set(nodes) - cyc_set) | {new_node})
        deeper_incoming = cle(new_nodes, rt, tuple(contracted), depth + 1)

        # 4) expand: the external channel that enters the cycle ------------
        ext_cid = deeper_incoming.get(new_node)
        if ext_cid is None:
            raise NoArborescenceError(
                original_members,
                "contracted cycle received no incoming channel on expansion",
            )
        ext_edge = next(e for e in edges if e.cid == ext_cid)
        entered = ext_edge.dst
        removed_cid = best_in[entered].cid
        expansions.append(
            Expansion(
                depth=depth,
                supernode=new_node,
                cycle_nodes=list(cyc),
                removed_cid=removed_cid,
                added_cid=ext_cid,
                entered_node=entered,
                external_source=ext_edge.src,
            )
        )

        # Translate the deeper solution one level up.
        incoming: dict[int, int] = {}
        for v in nodes:
            if v == rt:
                continue
            if v == entered:
                incoming[v] = ext_cid
            elif v in cyc_set:
                incoming[v] = best_in[v].cid
            else:
                cid_v = deeper_incoming.get(v)
                if cid_v is not None:
                    incoming[v] = cid_v
        return incoming

    incoming = cle(frozenset(range(n)), root, tuple(channels), 0)

    selected = sorted(incoming.values())
    total_cost = sum(channels[c - 1].cost for c in selected)
    perturbed_total = sum(channels[c - 1].w for c in selected)

    # Decode/audit the perturbed objective:
    #   sum w = total_cost * SCALE - (bit vector of selected ids)
    bit_vector = sum(1 << (m - c) for c in selected)
    assert perturbed_total == total_cost * scale - bit_vector

    return ArborescenceResult(
        channels=channels,
        selected=selected,
        total_cost=total_cost,
        perturbed_total=perturbed_total,
        scale=scale,
        rounds=rounds,
        expansions=expansions,
    )
