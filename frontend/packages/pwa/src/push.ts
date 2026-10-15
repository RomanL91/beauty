import type { PushSubscriptionInput } from '@beauty/api';
import { useCallback, useState } from 'react';

/** Доступность push на устройстве. */
export type PushAvailability =
  /** Браузер не умеет Web Push. */
  | 'unsupported'
  /** iOS/iPadOS в браузере: push работает только у PWA с экрана «Домой». */
  | 'ios-install'
  /** Сборка без VAPID-ключа. */
  | 'no-key'
  | 'denied'
  | 'default'
  | 'granted';

/** iOS/iPadOS (iPadOS представляется как Mac с тачем). */
export function isIos(
  nav: Pick<Navigator, 'userAgent' | 'platform' | 'maxTouchPoints'> = navigator,
): boolean {
  return (
    /iPad|iPhone|iPod/.test(nav.userAgent) ||
    (nav.platform === 'MacIntel' && nav.maxTouchPoints > 1)
  );
}

/** Запущено ли как установленное PWA. */
export function isStandalone(): boolean {
  return (
    window.matchMedia?.('(display-mode: standalone)').matches === true ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

/** Что можно сделать с уведомлениями здесь и сейчас. */
export function detectPush(vapidKey: string | null): PushAvailability {
  if (typeof window === 'undefined') return 'unsupported';
  const ios = isIos();
  if (ios && !isStandalone()) return 'ios-install';
  if (
    !('Notification' in window) ||
    !('PushManager' in window) ||
    !('serviceWorker' in navigator)
  ) {
    return 'unsupported';
  }
  if (Notification.permission === 'denied') return 'denied';
  if (!vapidKey) return 'no-key';
  return Notification.permission === 'granted' ? 'granted' : 'default';
}

/** VAPID-ключ (base64url) → байты для `applicationServerKey`. */
export function vapidKeyToBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded =
    base64url.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

const SUBSCRIPTION_KEY = 'beauty.push.subscription';
const DISMISSED_KEY = 'beauty.push.dismissed';
const DISMISS_FOR_MS = 14 * 86_400_000;

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Параметры подписки. */
export interface PushOptions {
  readonly app: PushSubscriptionInput['app'];
  readonly masterSlug?: string;
  readonly vapidKey: string | null;
  /** Порт `PushGateway.register`. */
  readonly register: (input: PushSubscriptionInput) => Promise<string>;
}

/** Состояние подписки на уведомления. */
export interface PushState {
  readonly availability: PushAvailability;
  readonly subscribed: boolean;
  readonly busy: boolean;
  /** Отложено пользователем («Не сейчас») — плашку не показываем 14 дней. */
  readonly dismissed: boolean;
  readonly error: string | null;
}

/**
 * Подписка на Web Push: разрешение → `pushManager.subscribe` с VAPID-ключом →
 * сохранение подписки на сервере. Разрешение спрашиваем только по действию
 * пользователя (кнопка в плашке или настройках).
 */
export function usePushSubscription(options: PushOptions) {
  const [state, setState] = useState<PushState>(() => {
    const store = storage();
    const dismissedAt = Number(store?.getItem(DISMISSED_KEY) ?? 0);
    return {
      availability: detectPush(options.vapidKey),
      subscribed: Boolean(store?.getItem(SUBSCRIPTION_KEY)),
      busy: false,
      dismissed: Date.now() - dismissedAt < DISMISS_FOR_MS,
      error: null,
    };
  });
  const { app, masterSlug, vapidKey, register } = options;

  const subscribe = useCallback(async () => {
    if (!vapidKey) return;
    setState((s) => ({ ...s, busy: true, error: null }));
    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        setState((s) => ({
          ...s,
          busy: false,
          availability: permission === 'denied' ? 'denied' : 'default',
        }));
        return;
      }
      const registration = await Promise.race([
        navigator.serviceWorker.ready,
        new Promise<never>((_, reject) => setTimeout(() => reject(new Error('no-worker')), 5000)),
      ]);
      const subscription =
        (await registration.pushManager.getSubscription()) ??
        (await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: vapidKeyToBytes(vapidKey),
        }));
      const json = subscription.toJSON();
      const id = await register({
        app,
        ...(masterSlug && { master_slug: masterSlug }),
        endpoint: subscription.endpoint,
        expiration_time: subscription.expirationTime,
        keys: { p256dh: json.keys?.['p256dh'] ?? '', auth: json.keys?.['auth'] ?? '' },
      });
      storage()?.setItem(SUBSCRIPTION_KEY, id);
      setState((s) => ({ ...s, busy: false, subscribed: true, availability: 'granted' }));
    } catch {
      setState((s) => ({
        ...s,
        busy: false,
        error: 'Не получилось включить уведомления — попробуйте позже',
      }));
    }
  }, [app, masterSlug, vapidKey, register]);

  const dismiss = useCallback(() => {
    storage()?.setItem(DISMISSED_KEY, String(Date.now()));
    setState((s) => ({ ...s, dismissed: true }));
  }, []);

  return { ...state, subscribe, dismiss };
}
