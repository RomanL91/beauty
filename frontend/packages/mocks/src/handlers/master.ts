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

    ...settingsHandlers(db),

    http.get(
      '/me/events',
      ({ request, response }) =>
        requireBearer(request) ?? response.untyped(streamFromLog(db.masterLog, request)),
    ),
  ];
}

/** Поручения агенту (группа `assistant`): ответы приходят через мок-поток `/me/events`. */
export function assistantHandlers(db: MockDb) {
  return [
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
  ];
}

/** Настройки страницы: каждое изменение отвечает настройками целиком. */
function settingsHandlers(db: MockDb) {
  const settings = db.settings;
  const image = async (request: Request): Promise<{ file: Blob; alt: string } | null> => {
    const form = await request.formData().catch(() => null);
    const file = form?.get('file');
    if (!(file instanceof Blob)) return null;
    const alt = form?.get('alt');
    return { file, alt: typeof alt === 'string' ? alt : '' };
  };
  const noImage = () => problem(422, 'invalid_photo', 'Нужен файл в поле file');

  return [
    http.get('/me/broadcasts', async ({ request, response }) => {
      await delay(200);
      return requireBearer(request) ?? response(200).json(db.broadcasts.list());
    }),

    http.post('/me/broadcasts', async ({ request, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(250);
      const body = await request.json();
      return run(() => response(201).json(db.broadcasts.draft(body.text)));
    }),

    http.get('/me/broadcasts/{broadcast_id}', async ({ request, params, response }) => {
      await delay(150);
      return (
        requireBearer(request) ??
        run(() => response(200).json(db.broadcasts.get(params.broadcast_id)))
      );
    }),

    http.put('/me/broadcasts/{broadcast_id}', async ({ request, params, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(250);
      const body = await request.json();
      return run(() => response(200).json(db.broadcasts.edit(params.broadcast_id, body.text)));
    }),

    http.delete('/me/broadcasts/{broadcast_id}', async ({ request, params, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(200);
      return run(() => {
        db.broadcasts.discard(params.broadcast_id);
        return response(204).empty();
      });
    }),

    http.put('/me/broadcasts/{broadcast_id}/photo', async ({ request, params, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(350);
      const form = await request.formData();
      const file = form.get('file');
      if (!(file instanceof Blob))
        return problem(422, 'invalid_photo', 'Нужна картинка JPEG, PNG или WebP');
      return run(() => response(200).json(db.broadcasts.setPhoto(params.broadcast_id, file)));
    }),

    http.delete('/me/broadcasts/{broadcast_id}/photo', async ({ request, params, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(200);
      return run(() => response(200).json(db.broadcasts.removePhoto(params.broadcast_id)));
    }),

    http.post('/me/broadcasts/{broadcast_id}/send', async ({ request, params, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(300);
      return run(() => response(200).json(db.broadcasts.send(params.broadcast_id)));
    }),

    http.get('/me/clients', async ({ request, query, response }) => {
      await delay(200);
      return (
        requireBearer(request) ??
        response(200).json(
          db.clients.list({
            q: query.get('q'),
            filter: query.get('filter'),
            limit: intParam(query.get('limit'), 30),
            offset: intParam(query.get('offset'), 0),
          }),
        )
      );
    }),

    http.get('/me/clients/{client_id}', async ({ request, params, response }) => {
      await delay(200);
      return (
        requireBearer(request) ?? run(() => response(200).json(db.clients.card(params.client_id)))
      );
    }),

    http.put('/me/clients/{client_id}/name', async ({ request, params, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(250);
      const body = await request.json();
      return run(() => response(200).json(db.clients.rename(params.client_id, body.name ?? null)));
    }),

    http.post('/me/clients/{client_id}/notes', async ({ request, params, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(250);
      const body = await request.json();
      return run(() => response(201).json(db.clients.addNote(params.client_id, body.text)));
    }),

    http.delete(
      '/me/clients/{client_id}/notes/{note_id}',
      async ({ request, params, response }) => {
        const denied = requireBearer(request);
        if (denied) return denied;
        await delay(200);
        return run(() =>
          response(200).json(db.clients.removeNote(params.client_id, params.note_id)),
        );
      },
    ),

    http.get('/me/settings', async ({ request, response }) => {
      await delay(200);
      return requireBearer(request) ?? response(200).json(settings.view());
    }),

    http.put('/me/profile', async ({ request, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(250);
      const body = await request.json();
      return run(() => response(200).json(settings.updateProfile(body)));
    }),

    http.post('/me/services', async ({ request, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(250);
      const body = await request.json();
      return run(() => response(201).json(settings.addService(body)));
    }),

    http.put('/me/services/{service_id}', async ({ request, params, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(250);
      const body = await request.json();
      return run(() => response(200).json(settings.updateService(params.service_id, body)));
    }),

    http.delete('/me/services/{service_id}', async ({ request, params, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(250);
      return run(() => response(200).json(settings.archiveService(params.service_id)));
    }),

    http.put('/me/working-hours', async ({ request, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(250);
      const body = await request.json();
      return run(() => response(200).json(settings.setWorkingHours(body.days)));
    }),

    http.put('/me/days-off', async ({ request, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(250);
      const body = await request.json();
      return run(() => response(200).json(settings.setDaysOff(body.days)));
    }),

    http.put('/me/booking-rules', async ({ request, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(250);
      const body = await request.json();
      return run(() => response(200).json(settings.setBookingRules(body)));
    }),

    http.post('/me/photos', async ({ request, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(400);
      const upload = await image(request);
      if (!upload) return noImage();
      return run(() => response(201).json(settings.addPhoto(upload.file, upload.alt)));
    }),

    http.delete('/me/photos/{photo_id}', async ({ request, params, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(250);
      return run(() => response(200).json(settings.removePhoto(params.photo_id)));
    }),

    http.put('/me/avatar', async ({ request, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(400);
      const upload = await image(request);
      if (!upload) return noImage();
      return run(() => response(200).json(settings.setAvatar(upload.file)));
    }),

    http.delete('/me/avatar', async ({ request, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(250);
      return response(200).json(settings.setAvatar(null));
    }),

    http.post('/me/publish', async ({ request, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(250);
      return run(() => response(200).json(settings.publish()));
    }),

    http.post('/me/unpublish', async ({ request, response }) => {
      const denied = requireBearer(request);
      if (denied) return denied;
      await delay(250);
      return response(200).json(settings.unpublish());
    }),
  ];
}
