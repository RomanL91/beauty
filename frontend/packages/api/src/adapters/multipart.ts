import { ApiError } from '../http/api-error';
import { call, type HttpCore } from '../http/client';
import type { VoiceDraft } from '../ports/common';
import type { Message } from '../types';

/**
 * Отправить голосовое `multipart/form-data` (openapi-fetch для бинарных полей
 * неудобен, поэтому — напрямую через `fetch` с токеном).
 */
export async function postVoice(core: HttpCore, path: string, draft: VoiceDraft): Promise<Message> {
  const form = new FormData();
  form.set('client_id', draft.clientId);
  form.set('duration', String(Math.round(draft.duration * 10) / 10));
  form.set('audio', draft.audio, `voice.${extensionOf(draft.audio.type)}`);
  const response = await call(() =>
    core.authorizedFetch(new Request(core.url(path), { method: 'POST', body: form })),
  );
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw ApiError.fromBody(response.status, body);
  return body as Message;
}

function extensionOf(mime: string): string {
  if (mime.includes('mp4') || mime.includes('aac')) return 'm4a';
  if (mime.includes('ogg')) return 'ogg';
  return 'webm';
}
