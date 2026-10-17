import { describe, expect, it } from 'vitest';
import { createSseParser } from '../../src/lib/sse';

describe('createSseParser', () => {
  it('parses named events split across arbitrary chunks and ignores comments', () => {
    const events: Array<{ event: string; data: Record<string, unknown> }> = [];
    const parser = createSseParser((event) => events.push(event));
    parser.push(': connected\r\nevent: step\r\ndata: {"id":"step-1",');
    parser.push('"title":"Context loaded"}\r\n\r\nevent: done\ndata: {}\n\n');
    expect(events).toEqual([
      { event: 'step', data: { id: 'step-1', title: 'Context loaded' } },
      { event: 'done', data: {} },
    ]);
  });

  it('flushes a final frame without a trailing newline and falls back to raw data for invalid JSON', () => {
    const events: Array<{ event: string; data: Record<string, unknown> }> = [];
    const parser = createSseParser((event) => events.push(event));
    parser.push('event: message\ndata: first\ndata: second');
    parser.flush();
    expect(events).toEqual([{ event: 'message', data: { raw: 'first\nsecond' } }]);
  });
});
