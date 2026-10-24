import { describe, expect, it } from 'vitest';
import { applyEvent, initialLive } from './live';
import { mask, parseEvent, safeLink } from './api';
import type { ClaimEvent } from './types';
const event = (type: ClaimEvent['type'], data = {}): ClaimEvent => ({ type, agent: 'auditor', ts: '2026-10-24T10:00:00Z', text: 'test', data });
describe('live event state', () => {
  it('shows two send-backs then escalates without enabling review', () => {
    let state = applyEvent(initialLive, event('agent_start'));
    state = applyEvent(state, event('send_back', { retries: 1, send_back_to: 'damage' }));
    expect(state.retries).toBe(1); expect(state.target).toBe('damage');
    state = applyEvent(state, event('send_back', { retries: 2 }));
    state = applyEvent(state, event('escalate'));
    expect(state.retries).toBe(2); expect(state.phase).toBe('escalated');
  });
  it('requires interrupt for human review and handles errors', () => {
    expect(applyEvent(initialLive, event('agent_end')).phase).toBe('idle');
    expect(applyEvent(initialLive, event('interrupt')).phase).toBe('review');
    expect(applyEvent(initialLive, event('error')).phase).toBe('error');
    expect(applyEvent(initialLive, event('done')).phase).toBe('done');
  });
  it('does not mutate existing state or reduce known retries', () => {
    const state = applyEvent(initialLive, event('send_back', { retries: 2 }));
    expect(applyEvent(state, event('send_back', { retries: 1 })).retries).toBe(2);
    expect(initialLive.statuses).toEqual({});
  });
});
it('rejects malformed events and unsafe source links', () => {
  expect(() => parseEvent('{broken')).toThrow();
  expect(() => parseEvent('{"type":"surprise"}')).toThrow();
  expect(parseEvent(JSON.stringify(event('interrupt'))).type).toBe('interrupt');
  expect(safeLink('javascript:alert(1)')).toBeUndefined();
  expect(safeLink('file:///private/test')).toBeUndefined();
  expect(safeLink('https://example.com')).toBe('https://example.com');
});
it('masks short and full identifiers', () => {
  expect(mask('TEST0000')).toBe('•••• 0000');
  expect(mask('AB')).toBe('••••');
  expect(mask()).toBe('••••');
});
