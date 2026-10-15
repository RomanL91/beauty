/** Что клиент хотел сделать до входа (продолжаем после). */
export interface BookingIntent {
  readonly serviceId?: string;
  readonly start?: string;
}

/** Ссылка на чат с намерением записаться. */
export function chatHref(intent?: BookingIntent): string {
  if (!intent) return '/chat';
  const params = new URLSearchParams({ book: '1' });
  if (intent.serviceId) params.set('service', intent.serviceId);
  if (intent.start) params.set('slot', intent.start);
  return `/chat?${params.toString()}`;
}

/** Намерение из адреса чата. */
export function readIntent(search: URLSearchParams): BookingIntent | null {
  if (search.get('book') !== '1') return null;
  const serviceId = search.get('service') ?? undefined;
  const start = search.get('slot') ?? undefined;
  return { ...(serviceId && { serviceId }), ...(start && { start }) };
}

/** Ссылка на вход с возвратом. */
export function loginHref(returnTo: string): string {
  return `/login?return=${encodeURIComponent(returnTo)}`;
}

/** Безопасный путь возврата: только внутренний. */
export function safeReturn(value: string | null): string {
  return value && value.startsWith('/') && !value.startsWith('//') ? value : '/';
}
