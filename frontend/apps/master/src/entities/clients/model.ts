import type { ClientVisit, MasterClient } from '@beauty/api';
import { plural } from '../../shared/lib/plural';

/** Ключи кэша картотеки. */
export const clientKeys = {
  all: ['clients'] as const,
  list: (q: string, filter: 'all' | 'upcoming', limit: number) =>
    ['clients', 'list', q, filter, limit] as const,
  card: (id: string) => ['clients', 'card', id] as const,
};

export const MAX_NAME = 60;
export const MAX_NOTE = 500;

/** «3 визита», «визитов не было» (без рода: имя клиента может быть любым). */
export function visitsText(n: number): string {
  return n === 0 ? 'визитов не было' : `${n} ${plural(n, ['визит', 'визита', 'визитов'])}`;
}

/** «2 заметки». */
export function notesText(n: number): string {
  return `${n} ${plural(n, ['заметка', 'заметки', 'заметок'])}`;
}

const STATUS: Record<ClientVisit['status'], string> = {
  requested: 'Заявка',
  confirmed: 'Запись',
  completed: 'Был',
  cancelled: 'Отменена',
};

/** Подпись статуса визита; отмена — с тем, кто отменил. */
export function visitStatusText(visit: ClientVisit): string {
  if (visit.status !== 'cancelled') return STATUS[visit.status];
  if (visit.cancelled_by === 'client') return 'Отменил клиент';
  if (visit.cancelled_by === 'master') return 'Отменили вы';
  return 'Отклонена';
}

/** Тон бейджа статуса. */
export function visitTone(visit: ClientVisit): 'warn' | 'ok' | 'muted' | 'accent' {
  switch (visit.status) {
    case 'requested':
      return 'warn';
    case 'confirmed':
      return 'accent';
    case 'completed':
      return 'ok';
    default:
      return 'muted';
  }
}

/** Клиент без имени: в подписи по телефону нет имени, только цифры. */
export function isAnonymous(client: Pick<MasterClient, 'named'>): boolean {
  return !client.named;
}
