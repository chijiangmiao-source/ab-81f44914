"""Unit tests for the arborescence solver.

Includes a brute-force cross check: for small random multigraphs every
subset of incoming edges that forms a valid arborescence is enumerated, and
the solver output is compared with the true optimum (and the required
lexicographic tie break) directly.
"""

from __future__ import annotations

import itertools
import random

import pytest

from app.arboreal import Channel, NoArborescenceError, solve_arborescence


def make_channels(spec):
    """spec: list of (cid, src, dst, cost)."""
    m = len(spec)
    scale = 1 << m
    return [
        Channel(cid=c, src=s, dst=d, cost=w, w=w * scale - (1 << (m - c)))
        for c, s, d, w in spec
    ]


def brute_force_optimum(n, root, spec):
    """Return (min_cost, lexicographically-min sorted tuple of cids) or None."""
    by_dst: dict[int, list[tuple[int, int, int]]] = {v: [] for v in range(n)}
    for c, s, d, w in spec:
        by_dst[d].append((c, s, w))
    if root in by_dst:
        by_dst[root] = []
    targets = [v for v in range(n) if v != root]
    if any(not by_dst[v] for v in targets):
        return None
    domains = [by_dst[v] for v in targets]
    best = None
    for combo in itertools.product(*domains):
        parent = {v: s for v, (c, s, w) in zip(targets, combo)}
        # reachability from root
        seen = {root}
        changed = True
        while changed:
            changed = False
            for v in targets:
                if v not in seen and parent[v] in seen:
                    seen.add(v)
                    changed = True
        if len(seen) != n:
            continue
        cost = sum(w for c, s, w in combo)
        ids = tuple(sorted(c for c, s, w in combo))
        cand = (cost, ids)
        if best is None or cand < best:
            best = cand
    return best


def solve_ids(n, root, spec):
    res = solve_arborescence(n, root, make_channels(spec))
    return res.total_cost, tuple(res.selected)


def test_simple_tree():
    spec = [(1, 0, 1, 5), (2, 0, 2, 3), (3, 2, 1, 1)]
    cost, ids = solve_ids(3, 0, spec)
    assert cost == 4
    assert ids == (2, 3)


def test_single_cycle_contraction_and_expansion():
    # cycle 1->2 (cid2 cost1), 2->1 (cid1 cost1); root 0 enters via cid3 cost10
    spec = [
        (1, 2, 1, 1),
        (2, 1, 2, 1),
        (3, 0, 1, 10),
        (4, 0, 2, 10),
    ]
    res = solve_arborescence(3, 0, make_channels(spec))
    # Two cost-11 trees: enter cycle at node1 keep c2 -> ids (2,3);
    # enter at node2 keep c1 -> ids (1,4).  Lexicographic winner is (1,4).
    assert res.total_cost == 11
    assert tuple(res.selected) == (1, 4)
    assert len(res.rounds) == 2  # contracted round + base round
    assert res.rounds[0].cycle is not None
    assert res.expansions[0].removed_cid == 2
    assert res.expansions[0].added_cid == 4


def test_nested_cycles():
    """Two nested contraction levels on 5 nodes.

    Inner cycle: 1 -> 2 -> 1 (cids 1, 2)
    After contracting it to K5, an outer cycle appears:
        4 -> K5 (cid 3) and K5 -> 4 (cid 4)
    Root path 0 -> 3 (cid 5) -> 4 (cid 6) enters the outer cycle.
    """
    spec = [
        (1, 2, 1, 1),   # inner
        (2, 1, 2, 1),   # inner
        (3, 4, 1, 2),   # 4 -> inner node 1
        (4, 2, 4, 2),   # inner node 2 -> 4 (closes outer cycle)
        (5, 0, 3, 1),
        (6, 3, 4, 3),
    ]
    res = solve_arborescence(5, 0, make_channels(spec))
    # optimal: 0->3 (1), 3->4 (3), 4->1 (2), 1->2 (1) = 7
    assert res.total_cost == 7
    assert tuple(res.selected) == (2, 3, 5, 6)
    targets = {res.channels[c - 1].dst for c in res.selected}
    assert targets == {1, 2, 3, 4}
    fwd = {i: [] for i in range(5)}
    for c in res.selected:
        ch = res.channels[c - 1]
        fwd[ch.src].append(ch.dst)
    seen = {0}
    stack = [0]
    while stack:
        u = stack.pop()
        for v in fwd[u]:
            if v not in seen:
                seen.add(v)
                stack.append(v)
    assert seen == {0, 1, 2, 3, 4}
    # two contraction rounds recorded, shallow to deep
    depths = sorted(r.depth for r in res.rounds if r.cycle)
    assert depths == [0, 1]
    # two expansion replacements; outer first in record order (depth 1),
    # then inner (depth 0)
    assert [e.depth for e in res.expansions] == [1, 0]
    assert res.expansions[0].added_cid == 6
    assert res.expansions[0].removed_cid == 4
    assert res.expansions[1].added_cid == 3
    assert res.expansions[1].removed_cid == 1


def test_parallel_channels_pick_cheapest():
    spec = [(1, 0, 1, 7), (2, 0, 1, 3), (3, 0, 1, 5)]
    cost, ids = solve_ids(2, 0, spec)
    assert (cost, ids) == (3, (2,))


def test_tie_break_picks_smallest_first_id():
    # Two equal-cost trees: {c1, c2} vs {c2, c3}; must take (1, 2).
    spec = [
        (1, 0, 1, 5),   # 0->1
        (2, 0, 2, 0),   # 0->2
        (3, 2, 1, 5),   # 2->1 : alternative tree {c2,c3} also costs 5
    ]
    res = solve_arborescence(3, 0, make_channels(spec))
    assert res.total_cost == 5
    assert tuple(res.selected) == (1, 2)


def test_tie_break_with_parallel_entries():
    # Four equal-cost trees via parallel channels, all rooted directly at 0:
    # node1 via c1/c2 (cost1), node2 via c3/c6 (cost1).
    # Possible id lists: (1,3) (1,6) (2,3) (2,6); winner is (1,3).
    spec = [
        (1, 0, 1, 1),
        (2, 0, 1, 1),
        (3, 0, 2, 1),
        (4, 1, 2, 9),
        (5, 2, 1, 9),
        (6, 0, 2, 1),
    ]
    res = solve_arborescence(3, 0, make_channels(spec))
    assert res.total_cost == 2
    assert tuple(res.selected) == (1, 3)


def test_tie_break_through_cycle_sum_trap():
    """A tie that an id-*sum* perturbation must get wrong.

    Three valid trees, all cost 2:

      {c1, c6}: 0->2 (c6), 2->1 (c1)  ids sorted (1,6), id sum 7
      {c2, c3}: 0->1 (c2), 1->2 (c3)  ids sorted (2,3), id sum 5
      {c2, c6}: 0->1 (c2), 0->2 (c6)  ids sorted (2,6), id sum 8

    Lexicographic order ranks (1,6) first, although its id sum is the
    largest of the two competing tight trees.  The combination {c1, c3} is a
    1<->2 cycle with no root entry, hence invalid.
    """
    spec = [
        (1, 2, 1, 1),
        (2, 0, 1, 1),
        (3, 1, 2, 1),
        (4, 0, 1, 9),
        (5, 0, 2, 9),
        (6, 0, 2, 1),
    ]
    res = solve_arborescence(3, 0, make_channels(spec))
    assert res.total_cost == 2
    assert tuple(res.selected) == (1, 6)
    # a real contraction/expansion record must explain breaking the 2<->1 cycle
    assert res.expansions[0].added_cid in (1, 2, 6)


def test_unreachable_reports_nodes():
    # 4 nodes; node 3 completely isolated, node 2 reachable
    spec = [(1, 0, 1, 1), (2, 1, 2, 1)]
    with pytest.raises(NoArborescenceError) as ei:
        solve_arborescence(4, 0, make_channels(spec))
    assert ei.value.unreachable == [3]


def test_unreachable_behind_one_way_gap():
    spec = [(1, 0, 1, 1), (2, 2, 1, 1)]  # 2 points at 1, nobody reaches 2
    with pytest.raises(NoArborescenceError) as ei:
        solve_arborescence(3, 0, make_channels(spec))
    assert ei.value.unreachable == [2]


def test_zero_costs_allowed():
    spec = [(1, 0, 1, 0), (2, 1, 2, 0)]
    cost, ids = solve_ids(3, 0, spec)
    assert cost == 0
    assert ids == (1, 2)


@pytest.mark.parametrize("seed", range(60))
def test_random_graphs_against_brute_force(seed):
    rng = random.Random(seed)
    n = rng.randint(2, 5)
    root = 0
    max_edges = min(12, n * (n - 1))
    n_edges = rng.randint(n - 1, max_edges)
    spec = []
    used_pairs = set()
    cid = 0
    while len(spec) < n_edges:
        s = rng.randrange(n)
        d = rng.randrange(n)
        if s == d:
            continue
        # parallel edges allowed but keep pair multiplicity small
        key = (s, d)
        mult = sum(1 for c, a, b, w in spec if (a, b) == key)
        if mult >= 2:
            continue
        cid += 1
        spec.append((cid, s, d, rng.randint(0, 6)))
    best = brute_force_optimum(n, root, spec)
    if best is None:
        with pytest.raises(NoArborescenceError):
            solve_arborescence(n, root, make_channels(spec))
        return
    cost, ids = solve_ids(n, root, spec)
    assert (cost, ids) == best


def test_reduction_record_cost_consistency():
    spec = [
        (1, 2, 1, 4),
        (2, 1, 2, 3),
        (3, 0, 1, 10),
        (4, 0, 2, 20),
    ]
    res = solve_arborescence(3, 0, make_channels(spec))
    # entering at 1 (c3=10), keep c2 (1->2 cost3) => 13
    # entering at 2 (c4=20), keep c1 (2->1 cost4) => 24
    assert res.total_cost == 13
    assert tuple(res.selected) == (2, 3)
    exp = res.expansions[0]
    assert exp.added_cid == 3
    assert exp.removed_cid == 1
    # the expansion record literally explains the swap
    assert res.rounds[0].cycle["cycle_cost"] == 7
