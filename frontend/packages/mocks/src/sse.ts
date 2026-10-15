import type { EventLog } from './event-log';

const encoder = new TextEncoder();

/** Кадр SSE. */
export function frame(event: string, data: unknown, id?: string, retryMs?: number): Uint8Array {
  const lines: string[] = [];
  if (id !== undefined) lines.push(`id: ${id}`);
  lines.push(`event: ${event}`);
  if (retryMs !== undefined) lines.push(`retry: ${retryMs}`);
  lines.push(`data: ${JSON.stringify(data)}`);
  return encoder.encode(`${lines.join('\n')}\n\n`);
}

const HEADERS = {
  'Content-Type': 'text/event-stream',
  'Cache-Control': 'no-store',
  Connection: 'keep-alive',
};

/**
 * Ответ-поток SSE по журналу событий: досылает пропущенное после
 * `Last-Event-ID`, затем транслирует новые события и пингует.
 */
export function streamFromLog(log: EventLog, request: Request): Response {
  const lastId = request.headers.get('Last-Event-ID');
  let cleanup = (): void => undefined;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode('retry: 2000\n\n'));
      for (const e of log.since(lastId)) controller.enqueue(frame(e.event, e.data, e.id));
      const unsubscribe = log.subscribe((e) => {
        try {
          controller.enqueue(frame(e.event, e.data, e.id));
        } catch {
          cleanup();
        }
      });
      const ping = setInterval(() => {
        try {
          controller.enqueue(encoder.encode(': ping\n\n'));
        } catch {
          cleanup();
        }
      }, 15_000);
      cleanup = () => {
        unsubscribe();
        clearInterval(ping);
      };
      request.signal.addEventListener('abort', () => {
        cleanup();
        try {
          controller.close();
        } catch {
          /* уже закрыт */
        }
      });
    },
    cancel() {
      cleanup();
    },
  });
  return new Response(body, { headers: HEADERS });
}

/** Ответ-поток с заданной программой кадров (для статуса входа). */
export function streamFrom(
  request: Request,
  run: (emit: (chunk: Uint8Array) => void, close: () => void) => () => void,
): Response {
  let stop = (): void => undefined;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      let closed = false;
      const close = (): void => {
        if (closed) return;
        closed = true;
        stop();
        controller.close();
      };
      stop = run((chunk) => {
        if (!closed) controller.enqueue(chunk);
      }, close);
      request.signal.addEventListener('abort', close);
    },
    cancel() {
      stop();
    },
  });
  return new Response(body, { headers: HEADERS });
}
