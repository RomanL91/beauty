import type { PushSubscriptionInput } from '../types';

/** Порт подписок Web Push. */
export interface PushGateway {
  /** Сохранить подписку устройства; возвращает её `id`. */
  register(input: PushSubscriptionInput): Promise<string>;
  unregister(subscriptionId: string): Promise<void>;
}
