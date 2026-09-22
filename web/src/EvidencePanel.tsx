import type { ExpansionRecord, RoundRecord } from "./types";

interface EvidenceProps {
  rounds: RoundRecord[];
  expansions: ExpansionRecord[];
  onHoverChannels: (ids: string[]) => void;
  perturbation: Record<string, string>;
}

/**
 * Contraction/expansion audit trail.  Hovering a record highlights the
 * involved channels on the network graph (rounds name cycle channels,
 * expansions name the removed/added pair), linking evidence to the picture.
 */
export default function EvidencePanel(p: EvidenceProps) {
  return (
    <section className="panel evidence">
      <h2>收缩 / 展开可复算记录</h2>

      <details className="perturbation" open>
        <summary>字典序破同价的整数扰动（点击折叠）</summary>
        <dl className="kv">
          {Object.entries(p.perturbation).map(([k, v]) => (
            <div key={k} className="kv-row">
              <dt>{k}</dt>
              <dd title={String(v)}>
                {String(v).length > 72 ? String(v).slice(0, 69) + "…" : String(v)}
              </dd>
            </div>
          ))}
        </dl>
      </details>

      <h3>① 每轮选入与有向环收缩（递归下降）</h3>
      {p.rounds.length === 0 && (
        <div className="empty-hint">
          无：一次选出的最便宜入边已经成树，没有环，因此无需收缩。
        </div>
      )}
      {p.rounds.map((r) => (
        <div
          key={r.depth}
          className="record-card"
          onMouseEnter={() =>
            p.onHoverChannels(
              r.cycle ? r.cycle.channel_ids : r.choices.map((c) => c.channel_id)
            )
          }
          onMouseLeave={() => p.onHoverChannels([])}
        >
          <div className="record-head">第 {r.depth} 层 · 每个非根超点选最便宜入口</div>
          <ul className="choice-list">
            {r.choices.map((c) => (
              <li key={c.target + "|" + c.channel_id}>
                <code>
                  {c.source} → {c.target}
                </code>{" "}
                选用 <code>{c.channel_id}</code>（原始代价 {c.reduced_cost_part}
                ）
                {r.cycle && r.cycle.channel_ids.includes(c.channel_id) && (
                  <span className="tag tag-cycle">在环上</span>
                )}
              </li>
            ))}
          </ul>
          {r.cycle && (
            <div className="cycle-box">
              <div>
                发现有向环：
                {r.cycle.follow.map((f, i) => (
                  <span key={i}>
                    {" "}
                    <code>{f.from}</code>
                    <span className="arrow">→</span>
                    <code>{f.to}</code>
                    <em className="via">[{f.channel_id}]</em>
                    {i < r.cycle!.follow.length - 1 ? "，" : ""}
                  </span>
                ))}
              </div>
              <div className="muted">
                环上代价合计 {r.cycle.cycle_cost}；通道 {r.cycle.channel_ids.join(", ")}
              </div>
            </div>
          )}
          {r.contraction && (
            <div className="contract-box">
              收缩为超点 <code>{r.contraction.supernode}</code>（含原始点{" "}
              {r.contraction.original_points.join(", ")}），环内通道在下层消失。
            </div>
          )}
        </div>
      ))}

      <h3>② 展开替换（递归回升）</h3>
      {p.expansions.length === 0 && (
        <div className="empty-hint">无展开：没有发生过收缩。</div>
      )}
      {p.expansions.map((e, i) => (
        <div
          key={i}
          className="record-card expansion-card"
          onMouseEnter={() => p.onHoverChannels([e.removed_channel_id, e.added_channel_id])}
          onMouseLeave={() => p.onHoverChannels([])}
        >
          <div className="record-head">
            第 {e.depth} 层超点 {e.supernode} 展开
          </div>
          <div className="swap">
            <span className="swap-out">
              移除环上通道 <code>{e.removed_channel_id}</code>
            </span>
            <span className="swap-arrow">⇒</span>
            <span className="swap-in">
              换入外部通道 <code>{e.added_channel_id}</code>（
              {e.external_source} → {e.entered_point}）
            </span>
          </div>
          <div className="muted">其余环上通道保留，由此打破环并恢复可达性。</div>
        </div>
      ))}
    </section>
  );
}
