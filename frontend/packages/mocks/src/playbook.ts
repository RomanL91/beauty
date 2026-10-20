import type { Playbook, Practice, PracticeInput } from '@beauty/api';
import { MockProblem } from './errors';
import { uuidv7 } from './ids';

const MAX_TEXT = 500;
const MAX_PRACTICES = 200;

/** Что опыту мастера нужно от остального мока: услуги мастера (id → название). */
export interface PlaybookSource {
  services(): ReadonlyArray<{ readonly id: string; readonly title: string }>;
}

/**
 * Опыт мастера в моках — как на сервере: записи общие и к услуге, повтор того же текста —
 * та же запись, лимит 200, только к своим услугам; самостоятельность записи.
 */
export class MockPlaybook {
  #autoConfirm = false;
  #items: Array<Omit<Practice, 'service_title'>> = [
    {
      id: '0192a0c0-0000-7000-8000-000000000b01',
      text: 'Сложные массажи — с утра, к вечеру — короткие процедуры.',
      service_id: null,
      author: 'agent',
      created_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
      updated_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
    },
  ];

  constructor(private readonly source: PlaybookSource) {}

  get autoConfirm(): boolean {
    return this.#autoConfirm;
  }

  view(): Playbook {
    const services = this.source.services();
    const order = new Map(services.map((s, i) => [s.id, i]));
    const rank = (p: Omit<Practice, 'service_title'>) =>
      p.service_id === null ? -1 : (order.get(p.service_id) ?? services.length);
    return {
      auto_confirm: this.#autoConfirm,
      practices: [...this.#items]
        .sort((a, b) => rank(a) - rank(b) || a.created_at.localeCompare(b.created_at))
        .map((p) => ({
          ...p,
          service_title: services.find((s) => s.id === p.service_id)?.title ?? null,
        })),
    };
  }

  setAutonomy(autoConfirm: boolean): Playbook {
    this.#autoConfirm = autoConfirm;
    return this.view();
  }

  add(input: PracticeInput, author: Practice['author'] = 'master'): Playbook {
    const text = checked(input.text);
    const serviceId = input.service_id ?? null;
    this.#service(serviceId);
    const same = this.#items.find(
      (p) => p.service_id === serviceId && p.text.toLowerCase() === text.toLowerCase(),
    );
    if (same) return this.view();
    if (this.#items.length >= MAX_PRACTICES)
      throw new MockProblem(409, 'practices_limit', 'Слишком много записей — удалите устаревшие');
    const now = new Date().toISOString();
    this.#items = [
      ...this.#items,
      { id: uuidv7(), text, service_id: serviceId, author, created_at: now, updated_at: now },
    ];
    return this.view();
  }

  edit(id: string, input: PracticeInput): Playbook {
    const current = this.#find(id);
    const serviceId = input.service_id ?? null;
    if (serviceId !== current.service_id) this.#service(serviceId);
    const next = {
      ...current,
      text: checked(input.text),
      service_id: serviceId,
      updated_at: new Date().toISOString(),
    };
    this.#items = this.#items.map((p) => (p.id === id ? next : p));
    return this.view();
  }

  remove(id: string): Playbook {
    this.#find(id);
    this.#items = this.#items.filter((p) => p.id !== id);
    return this.view();
  }

  #find(id: string) {
    const found = this.#items.find((p) => p.id === id);
    if (!found) throw new MockProblem(404, 'practice_not_found', 'Запись не найдена');
    return found;
  }

  #service(id: string | null): void {
    if (id !== null && !this.source.services().some((s) => s.id === id))
      throw new MockProblem(404, 'service_not_found', 'У мастера нет такой услуги');
  }
}

function checked(text: string): string {
  const cleaned = text.trim();
  if (!cleaned || cleaned.length > MAX_TEXT)
    throw new MockProblem(422, 'invalid_practice', 'Запись — от 1 до 500 символов');
  return cleaned;
}
