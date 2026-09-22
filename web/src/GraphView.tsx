import { useMemo } from "react";
import type { ChannelInput } from "./types";

interface NodePos {
  name: string;
  x: number;
  y: number;
}

interface GraphViewProps {
  points: string[];
  root: string;
  channels: ChannelInput[];
  selectedIds: Set<string>;
  highlightIds: Set<string>;
  totalCost?: number;
}

const W = 760;
const H = 460;

/**
 * Hand-rolled deterministic layout (no graph library):
 * selected tree edges are layered by BFS depth from the root; channels not in
 * the tree are drawn dashed.  When no tree exists (unreachable case) every
 * point is placed on a circle.
 */
export default function GraphView(props: GraphViewProps) {
  const { points, root, channels, selectedIds, highlightIds } = props;

  const positions = useMemo<NodePos[]>(() => {
    const treeChildren = new Map<string, string[]>();
    for (const name of points) treeChildren.set(name, []);
    let hasTree = false;
    for (const ch of channels) {
      if (selectedIds.has(ch.id)) {
        treeChildren.get(ch.source)?.push(ch.target);
        hasTree = true;
      }
    }

    if (!hasTree || !points.includes(root)) {
      const cx = W / 2;
      const cy = H / 2;
      const r = Math.min(W, H) / 2 - 70;
      return points.map((name, i) => {
        const ang = (2 * Math.PI * i) / Math.max(points.length, 1) - Math.PI / 2;
        return { name, x: cx + r * Math.cos(ang), y: cy + r * Math.sin(ang) };
      });
    }

    // BFS layers from root over the selected tree.
    const depth = new Map<string, number>();
    depth.set(root, 0);
    const layers: string[][] = [[root]];
    const queue = [root];
    while (queue.length) {
      const u = queue.shift()!;
      const du = depth.get(u)!;
      for (const v of treeChildren.get(u) ?? []) {
        if (!depth.has(v)) {
          depth.set(v, du + 1);
          if (!layers[du + 1]) layers[du + 1] = [];
          layers[du + 1].push(v);
          queue.push(v);
        }
      }
    }
    // Defensive: any node missing from the tree goes to its own last layer.
    const maxD = layers.length;
    for (const name of points) {
      if (!depth.has(name)) {
        if (!layers[maxD]) layers[maxD] = [];
        layers[maxD].push(name);
        depth.set(name, maxD);
      }
    }

    const deepest = layers.length - 1;
    return points.map((name) => {
      const d = depth.get(name)!;
      const row = layers[d];
      const idx = row.indexOf(name);
      const x = deepest === 0 ? W / 2 : 70 + (d * (W - 140)) / deepest;
      const y = H / 2 + ((idx - (row.length - 1) / 2) * 92);
      return { name, x, y };
    });
  }, [points, root, channels, selectedIds]);

  const posOf = useMemo(() => {
    const m = new Map<string, NodePos>();
    for (const p of positions) m.set(p.name, p);
    return m;
  }, [positions]);

  const edgePath = (ch: ChannelInput) => {
    const a = posOf.get(ch.source);
    const b = posOf.get(ch.target);
    if (!a || !b) return null;
    // Parallel channels: perpendicular offset per channel on the same pair.
    const siblings = channels
      .filter((c) => c.source === ch.source && c.target === ch.target)
      .map((c) => c.id)
      .sort();
    const k = siblings.indexOf(ch.id);
    const spread = siblings.length > 1 ? (k - (siblings.length - 1) / 2) * 10 : 0;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    const nx = (-dy / len) * spread;
    const ny = (dx / len) * spread;
    // shorten at the node radius so the arrowhead is visible
    const ux = dx / len;
    const uy = dy / len;
    const x1 = a.x + ux * 26 + nx;
    const y1 = a.y + uy * 26 + ny;
    const x2 = b.x - ux * 26 + nx;
    const y2 = b.y - uy * 26 + ny;
    const curve = Math.abs(spread) < 1 ? 0 : 26;
    const mx = (x1 + x2) / 2 - (uy * curve) / 2 + nx;
    const my = (y1 + y2) / 2 + (ux * curve) / 2 + ny;
    return { d: `M ${x1} ${y1} Q ${mx} ${my} ${x2} ${y2}`, lx: mx, ly: my, x2, y2, ux, uy };
  };

  return (
    <div className="graph-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="汇流树网络图">
        <defs>
          <marker id="arrow-tree" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#1f7a4d" />
          </marker>
          <marker id="arrow-dim" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#9aa5b1" />
          </marker>
          <marker id="arrow-hot" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#d97706" />
          </marker>
        </defs>

        {channels.map((ch) => {
          const geo = edgePath(ch);
          if (!geo) return null;
          const selected = selectedIds.has(ch.id);
          const hot = highlightIds.has(ch.id);
          const cls = hot
            ? "edge edge-hot"
            : selected
            ? "edge edge-tree"
            : "edge edge-dim";
          const marker = hot ? "url(#arrow-hot)" : selected ? "url(#arrow-tree)" : "url(#arrow-dim)";
          return (
            <g key={ch.id} className={cls}>
              <path d={geo.d} fill="none" markerEnd={marker} />
              <text x={geo.lx} y={geo.ly - 4} textAnchor="middle" className="edge-label">
                {ch.id}·{ch.cost}
              </text>
            </g>
          );
        })}

        {positions.map((p) => (
          <g key={p.name}>
            <circle
              cx={p.x}
              cy={p.y}
              r={22}
              className={p.name === root ? "node node-root" : "node"}
            />
            <text x={p.x} y={p.y + 4} textAnchor="middle" className="node-label">
              {p.name}
            </text>
            {p.name === root && (
              <text x={p.x} y={p.y - 30} textAnchor="middle" className="root-tag">注入根</text>
            )}
          </g>
        ))}
      </svg>
      <div className="legend">
        <span><i className="sw sw-tree" /> 入选通道（标注 标识·代价）</span>
        <span><i className="sw sw-dim" /> 未入选通道</span>
        <span><i className="sw sw-hot" /> 记录联动高亮</span>
        {props.totalCost !== undefined && (
          <span className="total">规范树总代价：<b>{props.totalCost}</b></span>
        )}
      </div>
    </div>
  );
}
