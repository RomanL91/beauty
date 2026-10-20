import type {
  Appointment,
  ClientNote,
  ClientVisit,
  ConversationSummary,
  MasterClient,
  MasterClientCard,
  MasterClientPage,
  Service,
} from '@beauty/api';
import { MockProblem } from './errors';
import { uuidv7 } from './ids';
import { CLIENTS } from './fixtures/people';

const DAY = 24 * 60 * 60 * 1000;
const ANONYMOUS = 'Новый клиент · …';

/** Что картотеке нужно от остального мока: переписки, записи, услуги, переименование. */
export interface ClientsSource {
  roster(): ConversationSummary[];
  appointments(): Appointment[];
  services(): readonly Service[];
  /** Подпись клиента в чатах и графике. */
  relabel(clientId: string, label: string): void;
}

interface ClientFile {
  notes: ClientNote[];
}

/** Подпись без имени по маске телефона: «Новый клиент · …12 34». */
export function anonymousLabel(phoneMasked: string | undefined): string {
  return `${ANONYMOUS}${(phoneMasked ?? '').slice(-5)}`;
}

function note(text: string, author: ClientNote['author'], daysAgo: number): ClientNote {
  return {
    id: uuidv7(),
    text,
    author,
    created_at: new Date(Date.now() - daysAgo * DAY).toISOString(),
  };
}

/**
 * Картотека клиентов мастера в моках: клиенты — переписки мастера, визиты — его записи
 * плюс прошедшие визиты по номеру следующего визита (`visit_number`), имя и заметки — свои.
 */
export class MockClients {
  readonly #files = new Map<string, ClientFile>();

  constructor(private readonly source: ClientsSource) {
    this.#files.set(CLIENTS.darya.id, {
      notes: [
        note('Любит без музыки, приходит к 10:00', 'master', 20),
        note('Аллергия на лаванду — масла без неё', 'agent', 3),
      ],
    });
    this.#files.set(CLIENTS.marina.id, {
      notes: [note('Массаж средней силы, шея — осторожно', 'master', 40)],
    });
  }

  list(query: {
    q?: string | null;
    filter?: string | null;
    limit?: number;
    offset?: number;
  }): MasterClientPage {
    const needle = (query.q ?? '').trim().toLowerCase();
    const digits = needle.replace(/\D/g, '');
    const rows = this.source
      .roster()
      .map((c) => this.#row(c))
      .filter(
        (row) =>
          (needle === '' ||
            (row.named && row.display_name.toLowerCase().includes(needle)) ||
            (digits !== '' && row.phone_masked.replace(/\D/g, '').includes(digits))) &&
          (query.filter !== 'upcoming' || row.next_visit_at !== null),
      )
      .sort((a, b) => Date.parse(b.last_activity_at) - Date.parse(a.last_activity_at));
    const offset = query.offset ?? 0;
    return { items: rows.slice(offset, offset + (query.limit ?? 30)), total: rows.length };
  }

  card(clientId: string): MasterClientCard {
    const conversation = this.#conversation(clientId);
    const visits = this.#visits(conversation);
    const now = Date.now();
    const upcoming = visits
      .filter((v) => isOpen(v) && Date.parse(v.start) > now)
      .sort((a, b) => Date.parse(a.start) - Date.parse(b.start));
    const history = visits
      .filter((v) => !upcoming.includes(v))
      .sort((a, b) => Date.parse(b.start) - Date.parse(a.start))
      .slice(0, 30);
    return {
      ...this.#row(conversation),
      since: new Date(now - (conversation.client.visit_number * 21 + 14) * DAY).toISOString(),
      cancelled: visits.filter((v) => v.status === 'cancelled').length,
      upcoming,
      history,
      note_items: [...this.#file(clientId).notes].sort(
        (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
      ),
    };
  }

  rename(clientId: string, name: string | null): MasterClientCard {
    const conversation = this.#conversation(clientId);
    const cleaned = (name ?? '').split(/\s+/).filter(Boolean).join(' ');
    if (cleaned.length > 60)
      throw new MockProblem(422, 'invalid_client_name', 'Имя клиента — не длиннее 60 символов');
    this.source.relabel(clientId, cleaned || anonymousLabel(conversation.client.phone_masked));
    return this.card(clientId);
  }

  addNote(
    clientId: string,
    text: string,
    author: ClientNote['author'] = 'master',
  ): MasterClientCard {
    this.#conversation(clientId);
    const cleaned = text.trim();
    if (!cleaned || cleaned.length > 500)
      throw new MockProblem(422, 'invalid_client_note', 'Заметка — от 1 до 500 символов');
    const file = this.#file(clientId);
    if (!file.notes.some((n) => n.text.toLowerCase() === cleaned.toLowerCase())) {
      if (file.notes.length >= 100)
        throw new MockProblem(409, 'client_notes_limit', 'У клиента уже 100 заметок');
      file.notes.push(note(cleaned, author, 0));
    }
    return this.card(clientId);
  }

  removeNote(clientId: string, noteId: string): MasterClientCard {
    const file = this.#file(clientId);
    if (!file.notes.some((n) => n.id === noteId))
      throw new MockProblem(404, 'client_note_not_found', 'Заметка не найдена');
    file.notes = file.notes.filter((n) => n.id !== noteId);
    return this.card(clientId);
  }

  #conversation(clientId: string): ConversationSummary {
    const found = this.source.roster().find((c) => c.client.id === clientId);
    if (!found) throw new MockProblem(404, 'client_not_found', 'Клиент не найден');
    return found;
  }

  #file(clientId: string): ClientFile {
    let file = this.#files.get(clientId);
    if (!file) {
      file = { notes: [] };
      this.#files.set(clientId, file);
    }
    return file;
  }

  #row(conversation: ConversationSummary): MasterClient {
    const { client } = conversation;
    const visits = this.#visits(conversation);
    const now = Date.now();
    const done = visits.filter((v) => v.status === 'completed');
    const next = visits
      .filter((v) => isOpen(v) && Date.parse(v.start) > now)
      .map((v) => v.start)
      .sort()[0];
    const lastVisit =
      done
        .map((v) => v.start)
        .sort()
        .at(-1) ?? null;
    const activity = [conversation.last_message?.created_at, lastVisit]
      .filter((v): v is string => Boolean(v))
      .sort()
      .at(-1);
    return {
      id: client.id,
      conversation_id: conversation.id,
      display_name: client.display_name,
      named: !client.display_name.startsWith(ANONYMOUS),
      phone_masked: client.phone_masked ?? '',
      visits: done.length,
      last_visit_at: lastVisit,
      next_visit_at: next ?? null,
      notes: this.#file(client.id).notes.length,
      last_activity_at: activity ?? new Date(now - DAY).toISOString(),
    };
  }

  /** Записи клиента из графика и прошедшие визиты по его номеру визита. */
  #visits(conversation: ConversationSummary): ClientVisit[] {
    const { client } = conversation;
    const own = this.source
      .appointments()
      .filter((a) => a.client.id === client.id)
      .map((a): ClientVisit => ({
        id: a.id,
        status: a.status,
        start: a.start,
        end: a.end,
        service_title: a.service.title,
        price: a.service.price,
        ...(a.status === 'cancelled' ? { cancelled_by: a.cancelled_by } : {}),
      }));
    const services = this.source.services();
    const past = Array.from({ length: Math.max(0, client.visit_number - 1) }, (_, i) => {
      const service = services[(i + client.id.length) % services.length]!;
      const start = new Date(Date.now() - (i + 1) * 21 * DAY);
      start.setUTCHours(6, 0, 0, 0);
      return {
        id: `${client.id.slice(0, -4)}${String(9000 + i)}`,
        status: 'completed',
        start: start.toISOString(),
        end: new Date(start.getTime() + service.duration_min * 60_000).toISOString(),
        service_title: service.title,
        price: service.price,
      } satisfies ClientVisit;
    });
    return [...own, ...past];
  }
}

function isOpen(visit: ClientVisit): boolean {
  return visit.status === 'requested' || visit.status === 'confirmed';
}
