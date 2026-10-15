import { delay } from 'msw';
import type { ConversationFilter } from '@beauty/api';
import type { MockDb } from '../db';
import { streamFromLog } from '../sse';
import { http, intParam, problem, requireBearer, run } from './support';

const FILTERS: readonly ConversationFilter[] = ['all', 'needs_me', 'agent', 'me'];

/** Кабинет мастера. */
export function masterHandlers(db: MockDb) {
  return [
    http.get(
      '/me',
      ({ request, response }) => requireBearer(request) ?? response(200).json(db.page),
    ),

    http.get('/me/schedule', async ({ request, query, response }) => {
      await delay(200);
      const date = query.get('date') ?? '';
      if (!/^\d{4}-\d{2}-\d{2}$/.test(date))
        return problem(422, 'invalid_date', 'Дата в формате YYYY-MM-DD');
      return requireBearer(request) ?? response(200).json(db.daySchedule(date));
    }),

    http.post(
      '/me/appointments/{appointment_id}/confirm',
      async ({ request, params, response }) => {
        await delay(300);
        return (
          requireBearer(request) ??
          run(() => response(200).json(db.confirmAppointment(params.appointment_id)))
        );
      },
    ),

    http.post(
      '/me/appointments/{appointment_id}/decline',
      async ({ request, params, response }) => {
        await delay(300);
        const denied = requireBearer(request);
        if (denied) return denied;
        const body: { offer_alternatives?: boolean } =
          (await request.json().catch(() => null)) ?? {};
        return run(() =>
          response(200).json(
            db.declineAppointment(params.appointment_id, body.offer_alternatives ?? false),
          ),
        );
      },
    ),

    http.get('/me/conversations', async ({ request, query, response }) => {
      await delay(200);
      const raw = query.get('filter') ?? 'all';
      const filter = FILTERS.includes(raw) ? raw : 'all';
      return requireBearer(request) ?? response(200).json(db.inbox(filter, query.get('q')));
    }),

    http.get(
      '/me/conversations/{conversation_id}',
      ({ request, params, response }) =>
        requireBearer(request) ??
        run(() => response(200).json(db.conversation(params.conversation_id))),
    ),

    http.get(
      '/me/conversations/{conversation_id}/messages',
      async ({ request, params, query, response }) => {
        await delay(200);
        return (
          requireBearer(request) ??
          run(() =>
            response(200).json(
              db.dialogMessages(
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
      '/me/conversations/{conversation_id}/messages',
      async ({ request, params, response }) => {
        const denied = requireBearer(request);
        if (denied) return denied;
        await delay(250);
        const body = await request.json();
        return run(() =>
          response(201).json(
            db.sendMasterMessage(params.conversation_id, body.client_id, body.text),
          ),
        );
      },
    ),

    http.put(
      '/me/conversations/{conversation_id}/handler',
      async ({ request, params, response }) => {
        const denied = requireBearer(request);
        if (denied) return denied;
        const body = await request.json();
        return run(() =>
          response(200).json({ handler: db.setHandler(params.conversation_id, body.handler) }),
        );
      },
    ),

    http.get('/me/assistant/messages', async ({ request, query, response }) => {
      await delay(200);
      return (
        requireBearer(request) ??
        response(200).json(
          db.assistantMessages(query.get('before'), intParam(query.get('limit'), 30)),
        )
      );
    }),

    http.post('/me/assistant/messages', async ({ request, response }) => {
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
        return response(201).json(
          db.sendAssistantVoice(clientId, audio, Number(form.get('duration') ?? 0)),
        );
      }
      const body = await request.json();
      return response(201).json(db.sendAssistantText(body.client_id, body.text));
    }),

    http.post('/me/assistant/choices/{choice_id}', async ({ request, params, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(200);
      const body = await request.json();
      return run(() => response(200).json(db.chooseOption(params.choice_id, body.option_id)));
    }),

    http.get(
      '/me/events',
      ({ request, response }) =>
        requireBearer(request) ?? response.untyped(streamFromLog(db.masterLog, request)),
    ),
  ];
}
