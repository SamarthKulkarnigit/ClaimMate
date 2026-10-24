// Live agent workflow, drawn as a fixed-layout SVG (no runtime measuring -> it can never render blank).
import { ScanLine, Network, Camera, BookOpen, Calculator, ShieldCheck, UserRound, FileCheck2, Check } from 'lucide-react';
import type { Agent } from './types';
import type { LiveState, NodeStatus } from './live';

const W = 180, H = 92;
const agents = [
  ['intake', 'Evidence intake', 'EXIF + duplicate check', 0, 100, ScanLine],
  ['coordinator', 'Coordinator', 'Routes & re-checks', 220, 100, Network],
  ['damage', 'Damage assessor', 'Parts, severity, evidence', 440, 0, Camera],
  ['policy', 'Policy analyst', 'Coverage + citations', 440, 100, BookOpen],
  ['cost', 'Cost estimator', 'Fixed-rule calculations', 440, 200, Calculator],
  ['auditor', 'Auditor', '6 independent checks', 660, 100, ShieldCheck],
  ['human', 'Your review', 'Approve or reject', 880, 100, UserRound],
  ['finalize', 'Claim file', 'Report + email draft', 1100, 100, FileCheck2],
] as const;
const pos = Object.fromEntries(agents.map(([id, , , x, y]) => [id, { x, y }])) as Record<Agent, { x: number; y: number }>;
const links: [Agent, Agent][] = [['intake', 'coordinator'], ['coordinator', 'damage'], ['coordinator', 'policy'], ['coordinator', 'cost'],
  ['damage', 'auditor'], ['policy', 'auditor'], ['cost', 'auditor'], ['auditor', 'human'], ['human', 'finalize']];

function path(a: Agent, b: Agent) {
  const s = pos[a], t = pos[b];
  const sx = s.x + W, sy = s.y + H / 2, tx = t.x, ty = t.y + H / 2, dx = Math.max(30, (tx - sx) / 2);
  return `M ${sx} ${sy} C ${sx + dx} ${sy}, ${tx - dx} ${ty}, ${tx} ${ty}`;
}

export default function AgentGraph({ live }: { live: LiveState }) {
  const status = (id: Agent): NodeStatus => live.statuses[id] || 'waiting';
  const c = pos.coordinator, a = pos.auditor;
  const retryPath = `M ${a.x + W / 2} ${a.y} C ${a.x + W / 2} ${a.y - 195}, ${c.x + W / 2} ${c.y - 195}, ${c.x + W / 2} ${c.y}`;
  return (
    <div className="graph" aria-label="Live agent workflow" style={{ height: 'auto', padding: '14px 18px' }}>
      <style>{`
        .ag-edge{fill:none;stroke:#c7d4de;stroke-width:1.8}
        .ag-edge.done{stroke:#16a384}
        .ag-edge.active{stroke:#498fb5;stroke-dasharray:6 5;animation:ag-dash .7s linear infinite}
        .ag-retry{fill:none;stroke:#d98739;stroke-width:2.2;stroke-dasharray:7 5;animation:ag-dash .7s linear infinite}
        @keyframes ag-dash{to{stroke-dashoffset:-22}}
        .ag-svg .agent-node{width:${W}px;height:${H}px;box-sizing:border-box}
      `}</style>
      <svg className="ag-svg" viewBox={`-10 ${live.retries ? -82 : -10} ${1100 + W + 20} ${live.retries ? 392 : 320}`}
           width="100%" style={{ display: 'block', maxHeight: 340 }} preserveAspectRatio="xMidYMid meet" role="img">
        <defs>
          <marker id="ag-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#a9bac8" />
          </marker>
          <marker id="ag-arrow-retry" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#d98739" />
          </marker>
        </defs>
        {links.map(([s, t]) => {
          const cls = status(t) === 'running' ? 'active' : status(s) === 'complete' ? 'done' : '';
          return <path key={`${s}-${t}`} d={path(s, t)} className={`ag-edge ${cls}`} markerEnd="url(#ag-arrow)" />;
        })}
        {live.retries > 0 && <path d={retryPath} className="ag-retry" markerEnd="url(#ag-arrow-retry)" />}
        {live.retries > 0 && (
          <text x={(a.x + c.x + W) / 2} y={a.y - 160} textAnchor="middle" fontSize="13" fill="#b9732c" fontWeight={600}>
            Auditor sent work back · re-check {live.retries}
          </text>
        )}
        {agents.map(([id, label, subtitle, x, y, Icon]) => {
          const st = status(id);
          return (
            <foreignObject key={id} x={x} y={y} width={W} height={H}>
              <div className={`agent-node ${st} ${id === 'auditor' ? 'auditor-node' : ''}`}>
                <div className="agent-node-top"><Icon size={18} /><span>{st === 'complete' ? <Check size={14} /> : st}</span></div>
                <strong>{label}</strong><small>{subtitle}</small>
              </div>
            </foreignObject>
          );
        })}
      </svg>
    </div>
  );
}
