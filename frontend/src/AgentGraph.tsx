import { useEffect, useRef } from 'react';
import { ReactFlow, Background, Controls, Handle, Position, MarkerType, type NodeProps, type ReactFlowInstance } from '@xyflow/react';
import { ScanLine, Network, Camera, BookOpen, Calculator, ShieldCheck, UserRound, FileCheck2, Check } from 'lucide-react';
import type { Agent } from './types';
import type { LiveState, NodeStatus } from './live';
const agents = [
  ['intake', 'Evidence intake', 'EXIF + duplicate check', 0, 100, ScanLine],
  ['coordinator', 'Coordinator', 'Routes & re-checks', 210, 100, Network],
  ['damage', 'Damage assessor', 'Parts, severity, evidence', 430, 0, Camera],
  ['policy', 'Policy analyst', 'Coverage + citations', 430, 100, BookOpen],
  ['cost', 'Cost estimator', 'Fixed-rule calculations', 430, 200, Calculator],
  ['auditor', 'Auditor', '6 independent checks', 650, 100, ShieldCheck],
  ['human', 'Your review', 'Approve or reject', 870, 100, UserRound],
  ['finalize', 'Claim file', 'Report + email draft', 1090, 100, FileCheck2],
] as const;
function AgentNode({ data }: NodeProps) {
  const Icon = data.icon as typeof ShieldCheck;
  const status = data.status as NodeStatus;
  return <div className={`agent-node ${status} ${data.agent === 'auditor' ? 'auditor-node' : ''}`}>
    <Handle type="target" position={Position.Left} /><div className="agent-node-top"><Icon size={18}/><span>{status === 'complete' ? <Check size={14}/> : status}</span></div>
    <strong>{String(data.label)}</strong><small>{String(data.subtitle)}</small><Handle type="source" position={Position.Right}/>
  </div>;
}
const nodeTypes = { agent: AgentNode };
const FIT = { padding: .12, minZoom: .45, maxZoom: 1 };
export default function AgentGraph({ live }: { live: LiveState }) {
  const flow = useRef<ReactFlowInstance | null>(null);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current; if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => requestAnimationFrame(() => flow.current?.fitView(FIT)));
    ro.observe(el); return () => ro.disconnect();
  }, []);
  const nodes = agents.map(([id, label, subtitle, x, y, icon]) => ({ id, type: 'agent', position: { x, y }, data: { agent: id, label, subtitle, icon, status: live.statuses[id as Agent] || 'waiting' } }));
  const links = [['intake', 'coordinator'], ['coordinator', 'damage'], ['coordinator', 'policy'], ['coordinator', 'cost'], ['damage', 'auditor'], ['policy', 'auditor'], ['cost', 'auditor'], ['auditor', 'human'], ['human', 'finalize']];
  const edges = links.map(([source, target]) => ({ id: `${source}-${target}`, source, target, type: 'smoothstep', animated: live.statuses[target as Agent] === 'running', style: { stroke: live.statuses[source as Agent] === 'complete' ? '#16a384' : '#c7d4de', strokeWidth: 1.8 }, markerEnd: { type: MarkerType.ArrowClosed, color: '#a9bac8' } }));
  if (live.retries) edges.push({ id: 'retry', source: 'auditor', target: 'coordinator', type: 'smoothstep', animated: live.phase === 'running', style: { stroke: '#d98739', strokeWidth: 2 }, markerEnd: { type: MarkerType.ArrowClosed, color: '#d98739' } });
  return <div ref={box} className="graph" aria-label="Live agent workflow"><ReactFlow onInit={inst => { flow.current = inst as unknown as ReactFlowInstance; setTimeout(() => inst.fitView(FIT), 60); }} nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={FIT} nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} panOnDrag zoomOnScroll={false} minZoom={.4} maxZoom={1.3}><Background color="#d8e2eb" gap={20}/><Controls showInteractive={false}/></ReactFlow></div>;
}
