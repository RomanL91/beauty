import { ApiError } from '../http/api-error';
import { call, unwrap, type HttpCore } from '../http/client';
import type { BroadcastsGateway } from '../ports/broadcasts-gateway';
import type { Broadcast, BroadcastList } from '../types';

/** Адаптер рассылок мастера (`/me/broadcasts`). */
export class HttpBroadcastsGateway implements BroadcastsGateway {
  constructor(private readonly core: HttpCore) {}

  list(): Promise<BroadcastList> {
    return unwrap(() => this.core.api.GET('/me/broadcasts'));
  }

  get(broadcastId: string): Promise<Broadcast> {
    return unwrap(() =>
      this.core.api.GET('/me/broadcasts/{broadcast_id}', this.#path(broadcastId)),
    );
  }

  draft(text: string): Promise<Broadcast> {
    return unwrap(() => this.core.api.POST('/me/broadcasts', { body: { text } }));
  }

  edit(broadcastId: string, text: string): Promise<Broadcast> {
    return unwrap(() =>
      this.core.api.PUT('/me/broadcasts/{broadcast_id}', {
        ...this.#path(broadcastId),
        body: { text },
      }),
    );
  }

  async discard(broadcastId: string): Promise<void> {
    await unwrap(() =>
      this.core.api.DELETE('/me/broadcasts/{broadcast_id}', this.#path(broadcastId)),
    );
  }

  async setPhoto(broadcastId: string, file: Blob): Promise<Broadcast> {
    const form = new FormData();
    form.set(
      'file',
      file,
      `photo.${file.type === 'image/png' ? 'png' : file.type === 'image/webp' ? 'webp' : 'jpg'}`,
    );
    const path = `/me/broadcasts/${encodeURIComponent(broadcastId)}/photo`;
    const response = await call(() =>
      this.core.authorizedFetch(new Request(this.core.url(path), { method: 'PUT', body: form })),
    );
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) throw ApiError.fromBody(response.status, body);
    return body as Broadcast;
  }

  removePhoto(broadcastId: string): Promise<Broadcast> {
    return unwrap(() =>
      this.core.api.DELETE('/me/broadcasts/{broadcast_id}/photo', this.#path(broadcastId)),
    );
  }

  send(broadcastId: string): Promise<Broadcast> {
    return unwrap(() =>
      this.core.api.POST('/me/broadcasts/{broadcast_id}/send', this.#path(broadcastId)),
    );
  }

  #path(broadcastId: string) {
    return { params: { path: { broadcast_id: broadcastId } } };
  }
}
