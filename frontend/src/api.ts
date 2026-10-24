import type { ClaimEvent, ClaimState, Demo, EventType } from './types';
export const API = (import.meta.env.VITE_API_BASE || '/api').replace(/\/$/, '');
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  if (!response.ok) throw new Error(`Request failed (${response.status}). Check that the ClaimMate backend is running.`);
  return response.json() as Promise<T>;
}
export const getClaim = (id: string) => request<ClaimState>(`/claims/${encodeURIComponent(id)}`);
export async function getDemos(): Promise<Demo[]> {
  const value = await request<(Demo | string)[] | { demos: (Demo | string)[] }>('/demo');
  return (Array.isArray(value) ? value : value.demos).map(item => typeof item === 'string'
    ? { name: item, title: item.replaceAll('_', ' '), description: 'Backend demo claim' } : item);
}
export const eventTypes: EventType[] = ['agent_start', 'agent_end', 'message', 'send_back', 'escalate', 'interrupt', 'done', 'error'];
export function parseEvent(raw: string): ClaimEvent {
  const value = JSON.parse(raw);
  if (!eventTypes.includes(value.type) || typeof value.agent !== 'string' || typeof value.text !== 'string' || typeof value.ts !== 'string') throw new Error('Invalid claim event');
  return { ...value, data: value.data && typeof value.data === 'object' ? value.data : {} };
}
export function watchClaim(id: string, onEvent: (event: ClaimEvent) => void, onError: (message: string) => void, onOpen: () => void) {
  const source = new EventSource(`${API}/claims/${encodeURIComponent(id)}/events`);
  source.onopen = onOpen;
  const receive = (message: MessageEvent) => {
    try { onEvent(parseEvent(message.data)); }
    catch { onError('An unreadable live update was received. Reconnect to reload claim state.'); }
  };
  source.onmessage = receive;
  // Both default SSE messages and explicit `event: agent_start` framing are supported.
  eventTypes.filter(type => type !== 'message').forEach(type => source.addEventListener(type, event => {
    if (event instanceof MessageEvent) receive(event);
  }));
  source.onerror = () => onError('Live connection interrupted. Reconnecting automatically…');
  return () => source.close();
}
export const mask = (value?: string) => !value || value.length <= 4 ? '••••' : `•••• ${value.slice(-4)}`;
export function redact(text: string, state?: ClaimState | null) {
  for (const value of [state?.vehicle?.reg_no, state?.policy?.policy_no]) if (value) text = text.split(value).join(mask(value));
  return text;
}
export const safeLink = (url?: string) => url && /^https?:\/\//i.test(url) ? url : undefined;
export const money = (value?: number) => value === undefined || !Number.isFinite(value) ? 'Pending' : new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(value);
export const title = (value: string) => value.replaceAll('_', ' ').replace(/\b\w/g, s => s.toUpperCase());
