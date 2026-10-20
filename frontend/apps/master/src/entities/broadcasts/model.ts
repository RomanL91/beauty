import { ApiError, type Broadcast } from '@beauty/api';
import { plural } from '../../shared/lib/plural';

export const broadcastKeys = {
  all: ['broadcasts'] as const,
  list: ['broadcasts', 'list'] as const,
  one: (id: string) => ['broadcasts', 'one', id] as const,
};

export const MAX_BROADCAST = 1000;

/** «37 клиентам». */
export function recipientsText(n: number): string {
  return `${n} ${plural(n, ['клиенту', 'клиентам', 'клиентам'])}`;
}

/** Статус рассылки для списка и карточки. */
export function broadcastStatusText(broadcast: Broadcast): string {
  switch (broadcast.status) {
    case 'draft':
      return 'Черновик';
    case 'sending':
      return `Отправляется · ${broadcast.delivered} из ${broadcast.recipients}`;
    case 'sent':
      return `Отправлено ${recipientsText(broadcast.delivered)}`;
  }
}

/** Ошибка отправки человеческим текстом. */
export function broadcastErrorText(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Не получилось — попробуйте ещё раз';
  if (error.isNetwork) return 'Нет соединения — рассылка не отправлена';
  switch (error.code) {
    case 'broadcast_cooldown':
      return 'Не чаще одной рассылки в сутки — попробуйте позже';
    case 'broadcasts_blocked':
      return 'Рассылки для вашей страницы отключены администрацией сервиса';
    case 'no_recipients':
      return 'Пока некому отправить: клиентов ещё нет';
    case 'broadcast_not_draft':
      return 'Эта рассылка уже отправлена';
    case 'photo_too_large':
      return 'Фото больше 8 МБ';
    case 'invalid_photo':
      return 'Нужна картинка JPEG, PNG или WebP';
    default:
      return error.message || 'Не получилось — попробуйте ещё раз';
  }
}
