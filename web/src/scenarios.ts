import type { SolveRequest } from "./types";

export interface Scenario {
  key: string;
  title: string;
  description: string;
  request: SolveRequest;
}

// Kept in sync with ../verify/scenarios.json (the verify service checks both
// against the live API).
export const SCENARIOS: Scenario[] = [
  {
    key: "nested",
    title: "嵌套环（两层收缩）",
    description:
      "a<->b 构成内环，收缩后与 d 形成外环；根 R 经 c 进入，需要两次收缩与两次展开。",
    request: {
      points: ["R", "a", "b", "c", "d"],
      root: "R",
      channels: [
        { id: "c1", source: "b", target: "a", cost: 1 },
        { id: "c2", source: "a", target: "b", cost: 1 },
        { id: "c3", source: "d", target: "a", cost: 2 },
        { id: "c4", source: "b", target: "d", cost: 2 },
        { id: "c5", source: "R", target: "c", cost: 1 },
        { id: "c6", source: "c", target: "d", cost: 3 },
      ],
    },
  },
  {
    key: "parallel",
    title: "平行通道",
    description: "A->B 三条平行通道，p2 与 p3 同价 2，字典序取 p2。",
    request: {
      points: ["A", "B"],
      root: "A",
      channels: [
        { id: "p1", source: "A", target: "B", cost: 5 },
        { id: "p2", source: "A", target: "B", cost: 2 },
        { id: "p3", source: "A", target: "B", cost: 2 },
      ],
    },
  },
  {
    key: "tie",
    title: "同优规范树（字典序破同价）",
    description:
      "三棵总价 2 的树：(t1,t6)、(t2,t3)、(t2,t6)。(t1,t6) 虽 id 之和最大，却字典序最小，必须入选。",
    request: {
      points: ["A", "B", "C"],
      root: "A",
      channels: [
        { id: "t1", source: "C", target: "B", cost: 1 },
        { id: "t2", source: "A", target: "B", cost: 1 },
        { id: "t3", source: "B", target: "C", cost: 1 },
        { id: "t4", source: "A", target: "B", cost: 9 },
        { id: "t5", source: "A", target: "C", cost: 9 },
        { id: "t6", source: "A", target: "C", cost: 1 },
      ],
    },
  },
  {
    key: "unreachable",
    title: "不可达点（无解）",
    description:
      "唯一通道 y->x 与根 R 完全分离，x、y 均不可达；提交后返回原因，输入保留。",
    request: {
      points: ["R", "x", "y"],
      root: "R",
      channels: [{ id: "u1", source: "y", target: "x", cost: 1 }],
    },
  },
];

export const DEFAULT_REQUEST: SolveRequest = SCENARIOS[0].request;
