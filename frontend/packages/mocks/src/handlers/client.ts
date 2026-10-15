import { delay } from 'msw';
import type { ClientMessageInput } from '@beauty/api';
import type { MockDb } from '../db';
import { streamFromLog } from '../sse';
import { http, intParam, problem, requireBearer, run } from './support';

/** Переписка и записи клиента. */
export function clientHandlers(db: MockDb) {
  return [
    http.get(
      '/conversations/me',
      ({ request, query, response }) =>
        requireBearer(request) ??
        run(() => response(200).json(db.clientConversation(query.get('master') ?? ''))),
    ),
    http.post(
      '/conversations/me',
      ({ request, query, response }) =>
        requireBearer(request) ??
        run(() => response(200).json(db.clientConversation(query.get('master') ?? ''))),
    ),

    http.get(
      '/conversations/{conversation_id}/messages',
      async ({ request, params, query, response }) => {
        await delay(200);
        return (
          requireBearer(request) ??
          run(() =>
            response(200).json(
              db.clientMessages(
                params.conversation_id,
                query.get('before'),
                intParam(query.get('limit'), 30),
              ),
            ),
          )
        );
      },
    ),

    http.post(
      '/conversations/{conversation_id}/messages',
      async ({ request, params, response }) => {
        const denied = requireBearer(request);
        if (denied) return denied;
        await delay(250);
        const type = request.headers.get('Content-Type') ?? '';
        if (type.startsWith('multipart/form-data')) {
          const form = await request.formData();
          const audio = form.get('audio');
          const clientId = form.get('client_id');
          if (!(audio instanceof Blob) || typeof clientId !== 'string') {
            return problem(422, 'invalid_voice', 'Нужны поля audio и client_id');
          }
          if (audio.size > 5 * 1024 * 1024)
            return problem(413, 'voice_too_large', 'Голосовое больше 5 МБ');
          const duration = Number(form.get('duration') ?? 0);
          return run(() =>
            response(201).json(
              db.sendClientVoice(params.conversation_id, clientId, audio, duration),
            ),
          );
        }
        const input = (await request.json()) as ClientMessageInput;
        return run(() => response(201).json(db.sendClientMessage(params.conversation_id, input)));
      },
    ),

    http.get(
      '/conversations/{conversation_id}/events',
      ({ request, params, response }) =>
        requireBearer(request) ??
        run(() => {
          if (params.conversation_id !== db.clientConversationId) {
            return problem(404, 'conversation_not_found', 'Переписка не найдена');
          }
          return response.untyped(streamFromLog(db.clientLog, request));
        }),
    ),

    http.post(
      '/appointments/{appointment_id}/cancel',
      ({ request, params, response }) =>
        requireBearer(request) ??
        run(() => response(200).json(db.cancelClientAppointment(params.appointment_id))),
    ),

    http.post(
      '/appointments/{appointment_id}/reschedule',
      async ({ request, params, response }) => {
        const denied = requireBearer(request);
        if (denied) return denied;
        const body = await request.json();
        return run(() =>
          response(200).json(db.rescheduleClientAppointment(params.appointment_id, body.start)),
        );
      },
    ),
  ];
}
