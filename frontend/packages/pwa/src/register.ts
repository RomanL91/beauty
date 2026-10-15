import { registerSW } from 'virtual:pwa-register';

/**
 * Зарегистрировать service worker PWA.
 *
 * В mock-режиме место service worker занимает MSW (у одного scope может быть
 * только один worker), поэтому PWA-worker там не регистрируется.
 */
export function registerPwa(options: { readonly enabled: boolean }): void {
  if (!options.enabled || !('serviceWorker' in navigator)) return;
  registerSW({ immediate: true });
}

/** Очистить кэш данных API в service worker (при выходе из аккаунта). */
export function clearApiCache(): void {
  navigator.serviceWorker?.controller?.postMessage('clear-api-cache');
}
