import type { Agent, ClaimEvent } from './types';
export type NodeStatus = 'waiting' | 'running' | 'complete' | 'review' | 'failed';
export interface LiveState { statuses: Partial<Record<Agent, NodeStatus>>; retries: number; phase: 'idle' | 'running' | 'review' | 'escalated' | 'done' | 'error'; target?: string }
export const initialLive: LiveState = { statuses: {}, retries: 0, phase: 'idle' };
export function applyEvent(state: LiveState, event: ClaimEvent): LiveState {
  const next = { ...state, statuses: { ...state.statuses } };
  if (event.type === 'agent_start') { next.statuses[event.agent] = 'running'; next.phase = 'running'; }
  if (event.type === 'agent_end') next.statuses[event.agent] = 'complete';
  if (event.type === 'send_back') {
    next.statuses.auditor = 'review';
    next.retries = typeof event.data.retries === 'number' ? Math.max(next.retries, event.data.retries) : next.retries + 1;
    next.target = String(event.data.send_back_to || 'damage');
    next.phase = 'running';
  }
  if (event.type === 'interrupt') { next.phase = 'review'; next.statuses.human = 'review'; }
  if (event.type === 'escalate') { next.phase = 'escalated'; next.statuses.auditor = 'failed'; }
  if (event.type === 'done') { next.phase = 'done'; next.statuses.finalize = 'complete'; }
  if (event.type === 'error') { next.phase = 'error'; next.statuses[event.agent] = 'failed'; }
  return next;
}
