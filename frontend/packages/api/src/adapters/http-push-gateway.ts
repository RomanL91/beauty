import { unwrap, type HttpCore } from '../http/client';
import type { PushGateway } from '../ports/push-gateway';
import type { PushSubscriptionInput } from '../types';

/** Адаптер подписок Web Push. */
export class HttpPushGateway implements PushGateway {
  constructor(private readonly core: HttpCore) {}

  async register(input: PushSubscriptionInput): Promise<string> {
    const created = await unwrap(() => this.core.api.POST('/push/subscriptions', { body: input }));
    return created.id;
  }

  async unregister(subscriptionId: string): Promise<void> {
    await unwrap(() =>
      this.core.api.DELETE('/push/subscriptions/{subscription_id}', {
        params: { path: { subscription_id: subscriptionId } },
      }),
    );
  }
}
