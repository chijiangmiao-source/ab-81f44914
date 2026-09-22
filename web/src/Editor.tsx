import type { ChannelInput } from "./types";

interface EditorProps {
  pointsText: string;
  root: string;
  channels: ChannelInput[];
  error: string | null;
  busy: boolean;
  onPoints: (v: string) => void;
  onRoot: (v: string) => void;
  onChangeChannel: (idx: number, patch: Partial<ChannelInput>) => void;
  onAddChannel: () => void;
  onRemoveChannel: (idx: number) => void;
  onSubmit: () => void;
  onLoadScenario: (key: string) => void;
  scenarioKey: string;
}

export default function Editor(p: EditorProps) {
  const pointList = p.pointsText
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);

  return (
    <section className="panel editor">
      <h2>输入</h2>

      <label className="field">
        <span>采样点（2–40 个唯一 ASCII，逗号或换行分隔）</span>
        <textarea
          rows={2}
          value={p.pointsText}
          onChange={(e) => p.onPoints(e.target.value)}
          spellCheck={false}
        />
      </label>

      <label className="field">
        <span>注入根</span>
        <select value={p.root} onChange={(e) => p.onRoot(e.target.value)}>
          {pointList.includes(p.root) ? null : <option value={p.root}>{p.root}（不在点集中）</option>}
          {pointList.map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>
      </label>

      <div className="field">
        <div className="chan-head">
          <span>有向通道（至多 160，标识唯一，代价为非负整数；允许平行、禁止自环）</span>
          <button type="button" className="btn-mini" onClick={p.onAddChannel}>＋ 增加通道</button>
        </div>
        <div className="chan-table">
          <div className="chan-row chan-th">
            <span>标识</span><span>源</span><span>目标</span><span>代价</span><span></span>
          </div>
          {p.channels.map((ch, i) => (
            <div className="chan-row" key={i}>
              <input
                value={ch.id}
                spellCheck={false}
                onChange={(e) => p.onChangeChannel(i, { id: e.target.value })}
              />
              <input
                value={ch.source}
                spellCheck={false}
                list="point-names"
                onChange={(e) => p.onChangeChannel(i, { source: e.target.value })}
              />
              <input
                value={ch.target}
                spellCheck={false}
                list="point-names"
                onChange={(e) => p.onChangeChannel(i, { target: e.target.value })}
              />
              <input
                value={Number.isFinite(ch.cost) ? ch.cost : 0}
                type="number"
                min={0}
                step={1}
                onChange={(e) => p.onChangeChannel(i, { cost: Number(e.target.value) })}
              />
              <button type="button" className="btn-mini danger" onClick={() => p.onRemoveChannel(i)}>删除</button>
            </div>
          ))}
          {p.channels.length === 0 && <div className="empty-hint">尚无通道</div>}
        </div>
        <datalist id="point-names">
          {pointList.map((n) => <option key={n} value={n} />)}
        </datalist>
      </div>

      {p.error && <div className="error-box">{p.error}</div>}

      <div className="actions">
        <button type="button" className="btn-primary" disabled={p.busy} onClick={p.onSubmit}>
          {p.busy ? "计算中…" : "提交到真实 API 求解"}
        </button>
        <div className="scenario-btns">
          {["nested", "parallel", "tie", "unreachable"].map((k) => (
            <button
              key={k}
              type="button"
              className={`btn-mini ${p.scenarioKey === k ? "active" : ""}`}
              onClick={() => p.onLoadScenario(k)}
            >
              {k}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
