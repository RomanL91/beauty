/** Событие канала с порядковым `id` (для `Last-Event-ID`). */
export interface LoggedEvent {
  readonly id: string;
  readonly event: string;
  readonly data: unknown;
}

type Listener = (event: LoggedEvent) => void;

/**
 * Журнал событий канала SSE: хранит историю, чтобы при переподключении
 * с `Last-Event-ID` дослать пропущенное, и раздаёт новые события подписчикам.
 */
export class EventLog {
  readonly #events: LoggedEvent[] = [];
  readonly #listeners = new Set<Listener>();
  #seq = 0;

  /** Опубликовать событие. */
  publish(event: string, data: unknown): LoggedEvent {
    this.#seq += 1;
    const logged: LoggedEvent = { id: String(this.#seq), event, data };
    this.#events.push(logged);
    if (this.#events.length > 500) this.#events.shift();
    for (const listener of this.#listeners) listener(logged);
    return logged;
  }

  /** События после указанного `id` (все — если `id` неизвестен или пуст). */
  since(lastId: string | null): LoggedEvent[] {
    if (lastId === null || lastId === '') return [];
    const after = Number(lastId);
    return Number.isFinite(after) ? this.#events.filter((e) => Number(e.id) > after) : [];
  }

  subscribe(listener: Listener): () => void {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  }
}
