import { uuidv7 } from '../ids';
import { http, requireBearer } from './support';

/** Подписки Web Push (в моках просто запоминаются). */
export function pushHandlers() {
  const subscriptions = new Map<string, string>();
  return [
    http.post('/push/subscriptions', async ({ request, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      const body = await request.json();
      const id = subscriptions.get(body.endpoint) ?? uuidv7();
      subscriptions.set(body.endpoint, id);
      return response(201).json({ id });
    }),
    http.delete(
      '/push/subscriptions/{subscription_id}',
      ({ request, response }) => requireBearer(request) ?? response(204).empty(),
    ),
  ];
}
