/// <reference lib="webworker" />
/**
 * Ядро service worker обоих PWA:
 *
 * * precache сборки (офлайн-оболочка SPA: навигации отдают `index.html`);
 * * данные API — network-first с кэшем на офлайн (кроме входа, SSE и мутаций);
 * * Web Push: показ уведомления и открытие нужного экрана по нажатию.
 */
import { clientsClaim } from 'workbox-core';
import { ExpirationPlugin } from 'workbox-expiration';
import {
  cleanupOutdatedCaches,
  createHandlerBoundToURL,
  precacheAndRoute,
} from 'workbox-precaching';
import { NavigationRoute, registerRoute } from 'workbox-routing';
import { NetworkFirst } from 'workbox-strategies';
import { safePath } from './safe-path';

declare const self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: Array<{ url: string; revision: string | null }>;
};

/** Кэш ответов API (чистится при выходе). */
export const API_CACHE = 'beauty-api';

/** Полезная нагрузка push (схема PushPayload контракта). */
interface PushPayload {
  readonly kind?: string;
  readonly title?: string;
  readonly body?: string;
  readonly url?: string;
  readonly tag?: string;
}

/** Настроить service worker; `manifest` — `self.__WB_MANIFEST` из точки входа. */
export function setupServiceWorker(
  manifest: Array<{ url: string; revision: string | null }>,
  options: { readonly defaultTitle: string },
): void {
  void self.skipWaiting();
  clientsClaim();
  cleanupOutdatedCaches();
  precacheAndRoute(manifest);

  registerRoute(
    new NavigationRoute(createHandlerBoundToURL('/index.html'), {
      denylist: [/^\/api\//, /^\/mockServiceWorker\.js$/],
    }),
  );

  registerRoute(
    ({ url, request }) =>
      url.origin === self.location.origin &&
      url.pathname.startsWith('/api/v1/') &&
      !url.pathname.startsWith('/api/v1/auth/') &&
      !url.pathname.endsWith('/events') &&
      request.method === 'GET' &&
      !(request.headers.get('Accept') ?? '').includes('text/event-stream'),
    new NetworkFirst({
      cacheName: API_CACHE,
      networkTimeoutSeconds: 6,
      plugins: [new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 7 * 86_400 })],
    }),
  );

  self.addEventListener('message', (event) => {
    if (event.data === 'clear-api-cache') event.waitUntil(caches.delete(API_CACHE));
  });

  self.addEventListener('push', (event) => {
    let payload: PushPayload;
    try {
      payload = (event.data?.json() as PushPayload | undefined) ?? {};
    } catch {
      payload = { body: event.data?.text() ?? '' };
    }
    event.waitUntil(
      self.registration.showNotification(payload.title ?? options.defaultTitle, {
        body: payload.body ?? '',
        icon: '/icons/icon-192.png',
        badge: '/icons/icon-192.png',
        lang: 'ru',
        ...(payload.tag && { tag: payload.tag }),
        data: { url: safePath(payload.url) },
      }),
    );
  });

  self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const path = safePath((event.notification.data as { url?: string } | null)?.url);
    const target = new URL(path, self.location.origin).href;
    event.waitUntil(
      (async () => {
        const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
        const existing = windows.find((w) => new URL(w.url).origin === self.location.origin);
        if (existing) {
          await existing.focus();
          await existing.navigate(target).catch(() => undefined);
          return;
        }
        await self.clients.openWindow(target);
      })(),
    );
  });
}
