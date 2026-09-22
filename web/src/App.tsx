import { useMemo, useState } from "react";
import Editor from "./Editor";
import EvidencePanel from "./EvidencePanel";
import GraphView from "./GraphView";
import { solve } from "./api";
import { DEFAULT_REQUEST, SCENARIOS } from "./scenarios";
import type { ChannelInput, SolveResponse } from "./types";

function pointsToText(points: string[]): string {
  return points.join(", ");
}

export default function App() {
  const [scenarioKey, setScenarioKey] = useState<string>("nested");
  const [pointsText, setPointsText] = useState<string>(pointsToText(DEFAULT_REQUEST.points));
  const [root, setRoot] = useState<string>(DEFAULT_REQUEST.root);
  const [channels, setChannels] = useState<ChannelInput[]>(
    DEFAULT_REQUEST.channels.map((c) => ({ ...c }))
  );
  // The submitted request is remembered so the graph/evidence always match
  // the last server answer, while the editors keep the (possibly invalid)
  // input untouched after a failure.
  const [submitted, setSubmitted] = useState<{
    points: string[];
    root: string;
    channels: ChannelInput[];
  } | null>(null);
  const [result, setResult] = useState<SolveResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<Set<string>>(new Set());

  const points = useMemo(
    () =>
      pointsText
        .split(/[\s,]+/)
        .map((s) => s.trim())
        .filter(Boolean),
    [pointsText]
  );

  const loadScenario = (key: string) => {
    const sc = SCENARIOS.find((s) => s.key === key);
    if (!sc) return;
    setScenarioKey(key);
    setPointsText(pointsToText(sc.request.points));
    setRoot(sc.request.root);
    setChannels(sc.request.channels.map((c) => ({ ...c })));
    setFormError(null);
  };

  const patchChannel = (idx: number, patch: Partial<ChannelInput>) =>
    setChannels((cs) => cs.map((c, i) => (i === idx ? { ...c, ...patch } : c)));

  const addChannel = () =>
    setChannels((cs) => [
      ...cs,
      { id: `e${cs.length + 1}`, source: points[0] ?? "", target: points[1] ?? "", cost: 1 },
    ]);

  const validateLocally = (): string | null => {
    if (points.length < 2 || points.length > 40)
      return `采样点数量必须在 2 至 40 之间（当前 ${points.length}）。`;
    if (new Set(points).size !== points.length) return "采样点标识必须唯一。";
    if (!points.includes(root)) return `注入根 ${root} 必须是采样点之一。`;
    if (channels.length > 160) return `通道至多 160 条（当前 ${channels.length}）。`;
    const ids = new Set<string>();
    for (let i = 0; i < channels.length; i++) {
      const ch = channels[i];
      if (!ch.id.trim()) return `第 ${i + 1} 条通道缺少唯一标识。`;
      if (ids.has(ch.id)) return `通道标识重复：${ch.id}`;
      ids.add(ch.id);
      if (!points.includes(ch.source)) return `通道 ${ch.id} 的源 ${ch.source} 不在点集中。`;
      if (!points.includes(ch.target)) return `通道 ${ch.id} 的目标 ${ch.target} 不在点集中。`;
      if (ch.source === ch.target) return `通道 ${ch.id} 是自环，禁止自环。`;
      if (!Number.isInteger(ch.cost) || ch.cost < 0)
        return `通道 ${ch.id} 的代价必须是非负整数。`;
    }
    return null;
  };

  const onSubmit = async () => {
    const err = validateLocally();
    if (err) {
      setFormError(err);
      return;
    }
    setFormError(null);
    setBusy(true);
    const req = { points, root, channels: channels.map((c) => ({ ...c })) };
    try {
      const body = await solve(req);
      // Input is intentionally retained: we never clear editors, including
      // after no-arborescence / validation failures from the server.
      setSubmitted(req);
      setResult(body);
      if (!body.ok) {
        setFormError(
          `${body.error?.message ?? "求解失败"}${
            body.unreachable.length ? `（不可达点：${body.unreachable.join(", ")}）` : ""
          }`
        );
      }
    } catch (e) {
      setSubmitted(req);
      setResult({
        ok: false,
        unreachable: [],
        error: { code: "network", message: `无法连接 API：${(e as Error).message}` },
      });
      setFormError(`网络/API 错误：${(e as Error).message}（输入已保留）`);
    } finally {
      setBusy(false);
    }
  };

  const selectedIds = useMemo(() => {
    const s = new Set<string>();
    if (result?.ok && result.tree) for (const e of result.tree.edges) s.add(e.channel_id);
    return s;
  }, [result]);

  const graphChannels = submitted?.channels ?? channels;
  const graphPoints = submitted?.points ?? points;
  const graphRoot = submitted?.root ?? root;

  return (
    <div className="app">
      <header className="app-header">
        <h1>冰川洞穴染料示踪 · 全局最小汇流树</h1>
        <p className="subtitle">
          自研 Chu–Liu/Edmonds 精确算法：最小化总代价；同优时取升序通道标识序列的字典序最小解，
          并给出每次有向环收缩、选入通道与展开替换的可复算记录。
        </p>
      </header>

      <div className="layout">
        <Editor
          pointsText={pointsText}
          root={root}
          channels={channels}
          error={formError}
          busy={busy}
          scenarioKey={scenarioKey}
          onPoints={setPointsText}
          onRoot={setRoot}
          onChangeChannel={patchChannel}
          onAddChannel={addChannel}
          onRemoveChannel={(i) => setChannels((cs) => cs.filter((_, idx) => idx !== i))}
          onSubmit={onSubmit}
          onLoadScenario={loadScenario}
        />

        <main className="results">
          {result?.ok && result.tree ? (
            <>
              <section className="panel">
                <h2>规范汇流树</h2>
                <GraphView
                  points={graphPoints}
                  root={graphRoot}
                  channels={graphChannels}
                  selectedIds={selectedIds}
                  highlightIds={highlight}
                  totalCost={result.tree.total_cost}
                />
                <table className="edge-table">
                  <thead>
                    <tr><th>通道标识</th><th>源</th><th>目标</th><th>代价</th></tr>
                  </thead>
                  <tbody>
                    {result.tree.edges.map((e) => (
                      <tr
                        key={e.channel_id}
                        onMouseEnter={() => setHighlight(new Set([e.channel_id]))}
                        onMouseLeave={() => setHighlight(new Set())}
                        className={highlight.has(e.channel_id) ? "row-hot" : ""}
                      >
                        <td><code>{e.channel_id}</code></td>
                        <td>{e.source}</td>
                        <td>{e.target}</td>
                        <td>{e.cost}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>

              <EvidencePanel
                rounds={result.evidence!.rounds}
                expansions={result.evidence!.expansions}
                onHoverChannels={(ids) => setHighlight(new Set(ids))}
                perturbation={result.evidence!.perturbation}
              />
            </>
          ) : (
            <section className="panel placeholder">
              <h2>网络图</h2>
              <GraphView
                points={graphPoints}
                root={graphRoot}
                channels={graphChannels}
                selectedIds={new Set()}
                highlightIds={highlight}
              />
              <p className="empty-hint">
                {result && !result.ok
                  ? "当前输入无规范树或被拒绝：上方给出了明确原因与不可达点，输入已保留，可修改后重新提交。"
                  : "提交后在此展示规范树、逐边代价与收缩证据。"}
              </p>
              {result && !result.ok && result.unreachable.length > 0 && (
                <div className="error-box">
                  不可达点：{result.unreachable.join(", ")}
                </div>
              )}
            </section>
          )}
        </main>
      </div>

      <footer className="app-footer">
        React + FastAPI · 不使用任何现成图优化库 · 端口与源均可通过环境变量配置
      </footer>
    </div>
  );
}
