import { ApiError, type Playbook, type Practice } from '@beauty/api';

export const playbookKeys = {
  all: ['playbook'] as const,
};

export const MAX_PRACTICE = 500;

/** Группа записей опыта: общие («Как вы работаете») или к одной услуге. */
export interface PracticeGroup {
  readonly key: string;
  readonly title: string;
  readonly items: readonly Practice[];
}

/** Записи по группам в порядке ответа сервера: общие, затем по услугам, убранные — в конце. */
export function practiceGroups(playbook: Playbook): PracticeGroup[] {
  const groups = new Map<string, { title: string; items: Practice[] }>();
  for (const practice of playbook.practices) {
    const key = practice.service_id ?? 'general';
    const title =
      practice.service_id === null
        ? 'Как вы работаете'
        : (practice.service_title ?? 'Услуга убрана');
    const group = groups.get(key) ?? { title, items: [] };
    group.items.push(practice);
    groups.set(key, group);
  }
  return [...groups].map(([key, group]) => ({ key, ...group }));
}

/** Ошибка изменения опыта человеческим текстом. */
export function playbookErrorText(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Не получилось — попробуйте ещё раз';
  if (error.isNetwork) return 'Нет соединения — изменения не сохранены';
  switch (error.code) {
    case 'invalid_practice':
      return 'Запись — от 1 до 500 символов';
    case 'practices_limit':
      return 'Записей слишком много — удалите устаревшие';
    case 'service_not_found':
      return 'Такой услуги уже нет';
    case 'practice_not_found':
      return 'Запись уже удалена';
    default:
      return 'Не получилось — попробуйте ещё раз';
  }
}
