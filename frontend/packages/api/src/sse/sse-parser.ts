/** Одно событие потока `text/event-stream`. */
export interface SseFrame {
  /** Имя события (`event:`), по умолчанию `message`. */
  readonly event: string;
  /** Склеенные строки `data:`. */
  readonly data: string;
  /** Последний `id:` потока (сохраняется между кадрами, как в EventSource). */
  readonly id: string | null;
}

/**
 * Инкрементальный разбор SSE по спецификации WHATWG.
 *
 * Принимает куски текста как есть (границы кадров могут приходить посередине),
 * поддерживает `\n`, `\r\n` и `\r`; комментарии (`: ping`) пропускает;
 * `retry:` передаёт отдельным колбэком.
 */
export class SseParser {
  #buffer = '';
  #afterCR = false;
  #event = '';
  #data: string[] = [];
  #lastId: string | null;

  constructor(
    private readonly onFrame: (frame: SseFrame) => void,
    private readonly onRetry: (ms: number) => void = () => undefined,
    initialId: string | null = null,
  ) {
    this.#lastId = initialId;
  }

  /** Последний полученный `id`. */
  get lastEventId(): string | null {
    return this.#lastId;
  }

  /** Подать очередной кусок текста. */
  push(chunk: string): void {
    // `\r` в конце прошлого куска и `\n` в начале этого — один перевод строки.
    const text = this.#afterCR && chunk.startsWith('\n') ? chunk.slice(1) : chunk;
    this.#afterCR = chunk.endsWith('\r');
    this.#buffer += text;
    const lines = this.#buffer.split(/\r\n|\r|\n/);
    this.#buffer = lines.pop() ?? '';
    for (const line of lines) this.#line(line);
  }

  #line(line: string): void {
    if (line === '') {
      this.#dispatch();
      return;
    }
    if (line.startsWith(':')) return;
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    switch (field) {
      case 'event':
        this.#event = value;
        break;
      case 'data':
        this.#data.push(value);
        break;
      case 'id':
        if (!value.includes('\0')) this.#lastId = value;
        break;
      case 'retry':
        if (/^\d+$/.test(value)) this.onRetry(Number(value));
        break;
      default:
        break;
    }
  }

  #dispatch(): void {
    if (this.#data.length > 0) {
      this.onFrame({
        event: this.#event || 'message',
        data: this.#data.join('\n'),
        id: this.#lastId,
      });
    }
    this.#event = '';
    this.#data = [];
  }
}
