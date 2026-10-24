import { afterEach, expect, it, vi } from 'vitest';
import { getDemos, request, watchClaim } from './api';
const envelope = { type: 'agent_end', agent: 'damage', ts: '2026-10-24T10:00:00Z', text: 'Done', data: {} };
afterEach(() => { vi.unstubAllGlobals(); });
it('uses the agreed request URL, method, and JSON error handling', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{"claim_id":"C1"}', {status:200}));
  vi.stubGlobal('fetch', fetchMock);
  expect(await request('/claims/C1/approve', {method:'POST',headers:{'Content-Type':'application/json'},body:'{"approved":true,"note":"ok"}'})).toEqual({claim_id:'C1'});
  expect(fetchMock.mock.calls[0][0]).toBe('/api/claims/C1/approve');
  expect(fetchMock.mock.calls[0][1].method).toBe('POST');
  fetchMock.mockResolvedValue(new Response('',{status:503}));
  await expect(request('/demo')).rejects.toThrow('503');
});
it('normalizes demo names and demo objects', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({demos:['clean_swift_front',{name:'x',title:'X',description:'Demo'}]}))));
  expect((await getDemos()).map(d => d.name)).toEqual(['clean_swift_front','x']);
});
it('accepts default and named SSE envelopes, reports invalid messages, and closes cleanly', () => {
  class FakeSource extends EventTarget {
    static current: FakeSource;
    onmessage?: (event: MessageEvent) => void;
    onerror?: () => void;
    onopen?: () => void;
    closed = false;
    constructor(public url: string) { super(); FakeSource.current = this; }
    close() { this.closed = true; }
  }
  vi.stubGlobal('EventSource', FakeSource);
  const onEvent=vi.fn(), onError=vi.fn(), onOpen=vi.fn();
  const close=watchClaim('C 1',onEvent,onError,onOpen);
  const source=FakeSource.current;
  expect(source.url).toBe('/api/claims/C%201/events');
  source.onopen?.(); expect(onOpen).toHaveBeenCalledOnce();
  source.onmessage?.(new MessageEvent('message',{data:JSON.stringify(envelope)}));
  source.dispatchEvent(new MessageEvent('agent_end',{data:JSON.stringify(envelope)}));
  expect(onEvent).toHaveBeenCalledTimes(2);
  source.onmessage?.(new MessageEvent('message',{data:'broken'}));
  expect(onError).toHaveBeenCalledOnce();
  source.onerror?.(); expect(onError).toHaveBeenCalledTimes(2);
  close(); expect(source.closed).toBe(true);
});
