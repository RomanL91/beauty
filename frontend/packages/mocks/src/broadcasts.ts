import type { Broadcast, BroadcastList } from '@beauty/api';
import { MockProblem } from './errors';
import { uuidv7 } from './ids';

const DAY = 24 * 60 * 60 * 1000;

/** Что рассылкам нужно от остального мока. */
export interface BroadcastsSource {
  /** Сколько у мастера клиентов (переписок). */
  recipients(): number;
  /** Объявление — в каждую переписку. */
  deliver(broadcast: Broadcast): void;
  storeUpload(file: Blob): string;
  later(run: () => void, ms?: number): void;
}

/** Последняя рассылка Алисы — 9 дней назад: лимит сейчас не мешает. */
function seed(): Broadcast[] {
  const started = new Date(Date.now() - 9 * DAY).toISOString();
  return [
    {
      id: '0192a0c0-0000-7000-8000-000000000a01',
      text: 'Открыла запись на ноябрь! Новинка — массаж лица 45 минут, первые три дня −15%.',
      photo_url: null,
      status: 'sent',
      origin: 'master',
      recipients: 5,
      delivered: 5,
      created_at: started,
      started_at: started,
      finished_at: started,
    },
  ];
}

/**
 * Рассылки в моках: черновики, фото (`blob:` URL), отправка с лимитом 24 ч и запретом
 * администрацией; доставка — через мгновение, объявление попадает во все переписки.
 */
export class MockBroadcasts {
  #items: Broadcast[] = seed();
  #blocked = false;

  constructor(private readonly source: BroadcastsSource) {}

  get allowed(): boolean {
    return !this.#blocked;
  }

  set allowed(value: boolean) {
    this.#blocked = !value;
  }

  /** Отправленные (для админ-панели). */
  sent(): Broadcast[] {
    return this.#items.filter((b) => b.started_at !== null);
  }

  list(): BroadcastList {
    return {
      items: this.#items.map((b) => this.#view(b)),
      allowed: !this.#blocked,
      next_at: this.#nextAt(),
    };
  }

  get(id: string): Broadcast {
    return this.#view(this.#find(id));
  }

  draft(text: string, origin: Broadcast['origin'] = 'master'): Broadcast {
    const now = new Date().toISOString();
    const broadcast: Broadcast = {
      id: uuidv7(),
      text: checked(text),
      photo_url: null,
      status: 'draft',
      origin,
      recipients: 0,
      delivered: 0,
      created_at: now,
      started_at: null,
      finished_at: null,
    };
    this.#items = [broadcast, ...this.#items];
    return this.#view(broadcast);
  }

  edit(id: string, text: string): Broadcast {
    this.#draft(id);
    return this.#change(id, { text: checked(text) });
  }

  discard(id: string): void {
    this.#draft(id);
    this.#items = this.#items.filter((b) => b.id !== id);
  }

  setPhoto(id: string, file: Blob): Broadcast {
    this.#draft(id);
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type))
      throw new MockProblem(422, 'invalid_photo', 'Нужна картинка JPEG, PNG или WebP');
    if (file.size > 8 * 1024 * 1024)
      throw new MockProblem(413, 'photo_too_large', 'Фото больше 8 МБ');
    return this.#change(id, { photo_url: this.source.storeUpload(file) });
  }

  removePhoto(id: string): Broadcast {
    this.#draft(id);
    return this.#change(id, { photo_url: null });
  }

  send(id: string): Broadcast {
    this.#draft(id);
    if (this.#blocked)
      throw new MockProblem(403, 'broadcasts_blocked', 'Рассылки отключены администрацией сервиса');
    if (this.#nextAt())
      throw new MockProblem(429, 'broadcast_cooldown', 'Не чаще одной рассылки в сутки');
    const recipients = this.source.recipients();
    if (recipients === 0)
      throw new MockProblem(409, 'no_recipients', 'Пока некому отправить: клиентов ещё нет');
    const sending = this.#change(id, {
      status: 'sending',
      recipients,
      started_at: new Date().toISOString(),
    });
    this.source.later(() => {
      const sent = this.#change(id, {
        status: 'sent',
        delivered: recipients,
        finished_at: new Date().toISOString(),
      });
      this.source.deliver(sent);
    }, 1200);
    return sending;
  }

  #nextAt(): string | null {
    const last = this.#items
      .map((b) => b.started_at)
      .filter((v): v is string => v !== null)
      .sort()
      .at(-1);
    if (!last) return null;
    const ready = Date.parse(last) + DAY;
    return ready > Date.now() ? new Date(ready).toISOString() : null;
  }

  #find(id: string): Broadcast {
    const found = this.#items.find((b) => b.id === id);
    if (!found) throw new MockProblem(404, 'broadcast_not_found', 'Рассылка не найдена');
    return found;
  }

  #draft(id: string): Broadcast {
    const found = this.#find(id);
    if (found.status !== 'draft')
      throw new MockProblem(409, 'broadcast_not_draft', 'Рассылка уже отправлена');
    return found;
  }

  #change(id: string, patch: Partial<Broadcast>): Broadcast {
    const next = { ...this.#find(id), ...patch };
    this.#items = this.#items.map((b) => (b.id === id ? next : b));
    return this.#view(next);
  }

  #view(broadcast: Broadcast): Broadcast {
    return broadcast.status === 'draft'
      ? { ...broadcast, recipients: this.source.recipients() }
      : broadcast;
  }
}

function checked(text: string): string {
  const cleaned = text.trim();
  if (!cleaned || cleaned.length > 1000)
    throw new MockProblem(422, 'invalid_broadcast', 'Текст рассылки — от 1 до 1000 символов');
  return cleaned;
}
