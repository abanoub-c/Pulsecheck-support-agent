import type { SseEvent } from './types';

export function createSseParser(onEvent: (event: SseEvent) => void) {
  let buffer = '';
  let eventName = 'message';
  let dataLines: string[] = [];

  const dispatch = () => {
    if (dataLines.length) {
      const raw = dataLines.join('\n');
      try {
        const data = JSON.parse(raw) as Record<string, unknown>;
        onEvent({ event: eventName, data });
      } catch {
        onEvent({ event: eventName, data: { raw } });
      }
    }
    eventName = 'message';
    dataLines = [];
  };

  const processLine = (line: string) => {
    if (line === '') { dispatch(); return; }
    if (line.startsWith(':')) return;
    const colon = line.indexOf(':');
    const field = colon < 0 ? line : line.slice(0, colon);
    const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '');
    if (field === 'event') eventName = value || 'message';
    if (field === 'data') dataLines.push(value);
  };

  return {
    push(chunk: string) {
      buffer += chunk;
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() ?? '';
      lines.forEach(processLine);
    },
    flush() {
      if (buffer) processLine(buffer);
      dispatch();
      buffer = '';
    },
  };
}

export async function consumeEventStream(response: Response, onEvent: (event: SseEvent) => void) {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'The message could not be sent.' })) as { error?: string };
    throw new Error(error.error || 'The message could not be sent.');
  }
  if (!response.body) throw new Error('Streaming is not available in this browser.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = createSseParser(onEvent);
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    parser.push(decoder.decode(value, { stream: true }));
  }
  parser.push(decoder.decode());
  parser.flush();
}
