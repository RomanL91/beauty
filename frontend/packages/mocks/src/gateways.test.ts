/**
 * Адаптеры `@beauty/api` против MSW-обработчиков: проверяем, что адаптеры
 * и моки говорят на одном контракте, и сценарии моков работают.
 */
import {
  ApiError,
  HttpAdminGateway,
  HttpAssistantGateway,
  HttpAuthGateway,
  HttpClientsGateway,
  HttpConversationGateway,
  HttpCore,
  HttpInboxGateway,
  HttpMasterEventsGateway,
  HttpMasterGateway,
  HttpMasterSettingsGateway,
  HttpScheduleGateway,
  StubMasterAuthGateway,
  type ChallengeStatus,
  type ConversationEvent,
  type MasterEvent,
  type MessageOf,
} from '@beauty/api';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import {
  CONVERSATIONS,
  DARYA_REQUEST_ID,
  DEMO_SLUG,
  MOCK_ADMIN_LOGIN,
  MOCK_ADMIN_PASSWORD,
} from './index';
import { createMockServer } from './node';
import { localDate } from './clock';

const { db, server } = createMockServer();

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => {
  server.close();
  db.dispose();
});

const ORIGIN = 'http://alisa.localhost';

function waitFor<T>(predicate: () => T | undefined, timeoutMs = 2000): Promise<T> {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const tick = (): void => {
      const value = predicate();
      if (value !== undefined) resolve(value);
      else if (Date.now() - started > timeoutMs) reject(new Error('timeout'));
      else setTimeout(tick, 10);
    };
    tick();
  });
}

describe('HttpAuthGateway', () => {
  it('вход: challenge → SSE статусы → обмен → сессия; refresh при старте', async () => {
    const core = new HttpCore({ origin: ORIGIN });
    const auth = new HttpAuthGateway(core);

    const challenge = await auth.startChallenge();
    expect(challenge.confirmation_code).toMatch(/^\d{2}$/);

    const seen: ChallengeStatus[] = [];
    const stop = auth.watchChallenge(challenge.challenge_id, { onStatus: (s) => seen.push(s) });
    await waitFor(() => (seen.includes('completed') ? true : undefined));
    stop();
    // Сколько шагов поток застанет, зависит от того, когда подключится SSE (под нагрузкой —
    // позже первого шага), поэтому проверяем порядок, а не полный список.
    const order = ['pending', 'claimed', 'confirmed', 'completed'];
    expect(seen.at(-1)).toBe('completed');
    expect(seen.map((s) => order.indexOf(s))).toEqual(
      [...seen.map((s) => order.indexOf(s))].sort(),
    );
    expect(new Set(seen).size).toBe(seen.length);

    await auth.exchangeChallenge(challenge.challenge_id);
    expect(core.session.getSnapshot().status).toBe('authenticated');

    const restored = new HttpCore({ origin: ORIGIN });
    await expect(new HttpAuthGateway(restored).restoreSession()).resolves.toBe(true);
    expect(restored.session.accessToken).toMatch(/^mock-access-/);
  });

  it('ошибка identity приходит как ApiError с кодом', async () => {
    const auth = new HttpAuthGateway(new HttpCore({ origin: ORIGIN }));
    const error = await auth
      .getChallengeStatus('0192a0c0-0000-7000-8000-000000000000')
      .catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, code: 'challenge_not_found' });
  });
});

/** Ядро с принятой мок-сессией. */
async function signedIn(): Promise<HttpCore> {
  const core = new HttpCore({ origin: ORIGIN });
  await new StubMasterAuthGateway(core).restoreSession();
  return core;
}

describe('HttpMasterGateway', () => {
  it('страница мастера и окна в будущем', async () => {
    const gw = new HttpMasterGateway(new HttpCore({ origin: ORIGIN }));
    const page = await gw.getPage(DEMO_SLUG);
    expect(page.display_name).toBe('Алиса Мельникова');
    expect(page.services).toHaveLength(4);

    const slots = await gw.listSlots(DEMO_SLUG, { limit: 4 });
    expect(slots).toHaveLength(4);
    for (const slot of slots) expect(Date.parse(slot.start)).toBeGreaterThan(Date.now());
  });

  it('неизвестный мастер → problem+json 404', async () => {
    const gw = new HttpMasterGateway(new HttpCore({ origin: ORIGIN }));
    await expect(gw.getPage('nobody')).rejects.toMatchObject({
      status: 404,
      code: 'master_not_found',
    });
  });
});

describe('HttpConversationGateway', () => {
  it('без сессии — 401', async () => {
    const gw = new HttpConversationGateway(new HttpCore({ origin: ORIGIN }));
    await expect(gw.open(DEMO_SLUG)).rejects.toMatchObject({ status: 401 });
  });

  it('запрос окон → slot_offer по SSE → выбор → карточка заявки', async () => {
    const gw = new HttpConversationGateway(await signedIn());
    const conversation = await gw.open(DEMO_SLUG);
    const history = await gw.listMessages(conversation.id, { limit: 3 });
    expect(history.items).toHaveLength(3);
    expect(history.has_more).toBe(true);

    const events: ConversationEvent[] = [];
    const ids: Array<string | null> = [];
    const stop = gw.subscribe(conversation.id, {
      onEvent: (e, id) => {
        events.push(e);
        ids.push(id);
      },
    });

    const sent = await gw.send(conversation.id, {
      kind: 'text',
      client_id: crypto.randomUUID(),
      text: 'Хочу записаться на массаж спины',
    });
    expect(sent.author).toBe('client');

    const offer = await waitFor(() =>
      events
        .flatMap((e) => ('message' in e ? [e.message] : []))
        .find(
          (m): m is MessageOf<'slot_offer'> => m.kind === 'slot_offer' && m.selected_start === null,
        ),
    );
    const slot = offer.slots[0]!;
    await gw.send(conversation.id, {
      kind: 'slot_pick',
      client_id: crypto.randomUUID(),
      offer_id: offer.id,
      start: slot.start,
    });

    const card = await waitFor(() =>
      events
        .flatMap((e) => ('message' in e ? [e.message] : []))
        .find((m): m is MessageOf<'booking_card'> => m.kind === 'booking_card'),
    );
    stop();
    expect(card.appointment.status).toBe('requested');
    expect(card.appointment.start).toBe(slot.start);
    expect(ids.every((id) => id !== null)).toBe(true);

    const cancelled = await gw.cancelAppointment(card.appointment.id);
    expect(cancelled.status).toBe('cancelled');
  });

  it('повтор с тем же client_id идемпотентен', async () => {
    const gw = new HttpConversationGateway(await signedIn());
    const { id } = await gw.open(DEMO_SLUG);
    const clientId = crypto.randomUUID();
    const a = await gw.send(id, { kind: 'text', client_id: clientId, text: 'Привет' });
    const b = await gw.send(id, { kind: 'text', client_id: clientId, text: 'Привет' });
    expect(b.id).toBe(a.id);
  });

  it('голосовое уходит multipart, расшифровка приходит обновлением', async () => {
    const gw = new HttpConversationGateway(await signedIn());
    const { id } = await gw.open(DEMO_SLUG);
    const events: ConversationEvent[] = [];
    const stop = gw.subscribe(id, { onEvent: (e) => events.push(e) });
    const voice = await gw.sendVoice(id, {
      clientId: crypto.randomUUID(),
      audio: new Blob([new Uint8Array(100)], { type: 'audio/webm' }),
      duration: 3.2,
    });
    expect(voice.kind).toBe('voice');
    const updated = await waitFor(() =>
      events
        .flatMap((e) => (e.type === 'message.updated' ? [e.message] : []))
        .find((m) => m.id === voice.id),
    );
    stop();
    expect(updated).toMatchObject({ kind: 'voice', transcript: expect.any(String) });
  });
});

describe('кабинет мастера', () => {
  it('график дня: заявка, окна, перерыв; подтверждение приходит событием', async () => {
    const core = await signedIn();
    const schedule = new HttpScheduleGateway(core);
    const day = await schedule.getDay(localDate(0));
    expect(day.summary.pending_requests).toBe(1);
    expect(day.items.map((i) => i.kind)).toEqual([
      'appointment',
      'free',
      'appointment',
      'free',
      'appointment',
      'break',
      'appointment',
      'free',
    ]);

    const events: MasterEvent[] = [];
    const stop = new HttpMasterEventsGateway(core).subscribe({ onEvent: (e) => events.push(e) });
    const confirmed = await schedule.confirm(DARYA_REQUEST_ID);
    expect(confirmed.status).toBe('confirmed');
    await waitFor(() => events.find((e) => e.type === 'appointment.updated'));
    stop();

    await expect(schedule.confirm(DARYA_REQUEST_ID)).rejects.toMatchObject({ status: 409 });
  });

  it('ответ мастера переводит диалог на «Я»', async () => {
    const inbox = new HttpInboxGateway(await signedIn());
    const list = await inbox.list('needs_me');
    expect(list.items.map((c) => c.client.display_name)).toContain('Новый клиент · …12 34');

    const result = await inbox.send(CONVERSATIONS.newcomer, {
      kind: 'text',
      client_id: crypto.randomUUID(),
      text: 'Сделаю скидку 10% вам обеим',
    });
    expect(result.handler).toBe('master');
    expect((await inbox.get(CONVERSATIONS.newcomer)).handler).toBe('master');
    await expect(inbox.setHandler(CONVERSATIONS.newcomer, 'agent')).resolves.toBe('agent');
  });

  it('поручение → выбор → прогресс по SSE до «Готово»', async () => {
    const core = await signedIn();
    const assistant = new HttpAssistantGateway(core);
    const events: MasterEvent[] = [];
    const stop = new HttpMasterEventsGateway(core).subscribe({ onEvent: (e) => events.push(e) });

    await assistant.sendText({
      kind: 'text',
      client_id: crypto.randomUUID(),
      text: 'Закрой воскресенье',
    });
    const choice = await waitFor(() =>
      events
        .flatMap((e) => (e.type === 'message.created' ? [e.message] : []))
        .find((m): m is MessageOf<'choice'> => m.kind === 'choice'),
    );
    const answered = await assistant.choose(choice.choice_id, 'yes');
    expect(answered).toMatchObject({ selected_option_id: 'yes' });

    const done = await waitFor(() =>
      events
        .flatMap((e) => (e.type === 'message.updated' ? [e.message] : []))
        .find((m) => m.kind === 'task_progress' && m.steps.every((s) => s.state === 'done')),
    );
    stop();
    expect(done).toMatchObject({ title: 'Готово' });
  });
});

describe('клиенты мастера', () => {
  it('список с поиском и фильтром; имя доходит до чатов; заметки без дублей', async () => {
    const core = await signedIn();
    const clients = new HttpClientsGateway(core);
    const all = await clients.list();
    expect(all.total).toBe(all.items.length);
    expect(all.items.length).toBeGreaterThan(3);
    const upcoming = await clients.list({ filter: 'upcoming' });
    expect(upcoming.items.every((c) => c.next_visit_at !== null)).toBe(true);
    const newcomer = (await clients.list({ q: '1234' })).items[0]!;
    expect(newcomer.named).toBe(false);

    const renamed = await clients.rename(newcomer.id, '  Сауле  ');
    expect([renamed.display_name, renamed.named]).toEqual(['Сауле', true]);
    const chats = await new HttpInboxGateway(core).list('all');
    expect(chats.items.some((c) => c.client.display_name === 'Сауле')).toBe(true);
    expect((await clients.list({ q: 'сау' })).items.map((c) => c.id)).toEqual([newcomer.id]);

    const noted = await clients.addNote(newcomer.id, 'Аллергия на лаванду');
    const again = await clients.addNote(newcomer.id, 'аллергия на лаванду');
    expect(again.note_items).toHaveLength(1);
    const cleared = await clients.removeNote(newcomer.id, noted.note_items[0]!.id);
    expect(cleared.note_items).toEqual([]);
    const reset = await clients.rename(newcomer.id, null);
    expect(reset.display_name).toBe('Новый клиент · …12 34');
    await expect(clients.card('00000000-0000-0000-0000-000000000000')).rejects.toMatchObject({
      status: 404,
      code: 'client_not_found',
    });
  });
});

describe('настройки страницы мастера', () => {
  it('профиль, услуга, график, выходной и правила видны на странице', async () => {
    const settings = new HttpMasterSettingsGateway(await signedIn());
    const page = new HttpMasterGateway(new HttpCore({ origin: ORIGIN }));
    const before = await settings.get();
    expect(before).toMatchObject({ status: 'published', publish_blockers: [] });

    await settings.updateProfile({
      ...before.page,
      about: 'Новый текст о себе',
    });
    expect((await page.getPage(DEMO_SLUG)).about).toBe('Новый текст о себе');

    const added = await settings.addService({
      title: 'Массаж лица',
      description: '  Лифтинг и лимфодренаж. ',
      duration_min: 45,
      price: { amount: 1_000_000, currency: 'KZT' },
    });
    const service = added.page.services.find((s) => s.title === 'Массаж лица');
    expect(service?.price?.amount).toBe(1_000_000);
    expect(service?.description).toBe('Лифтинг и лимфодренаж.');
    await expect(
      settings.addService({ title: 'x', duration_min: 7, price: null }),
    ).rejects.toMatchObject({ status: 422, code: 'invalid_service_duration' });
    const archived = await settings.archiveService(service!.id);
    expect(archived.page.services.some((s) => s.id === service!.id)).toBe(false);

    await expect(
      settings.setWorkingHours([
        {
          weekday: 0,
          intervals: [
            { start: '10:00', end: '14:00' },
            { start: '13:00', end: '15:00' },
          ],
        },
      ]),
    ).rejects.toMatchObject({ code: 'invalid_schedule' });
    const tomorrow = localDate(1);
    const off = await settings.setDaysOff([tomorrow, localDate(-3)]);
    expect(off.days_off).toEqual([tomorrow]);
    const slots = await page.listSlots(DEMO_SLUG, { limit: 50 });
    expect(slots.some((s) => s.start.startsWith(tomorrow))).toBe(false);
    await settings.setDaysOff([]);

    const rules = { ...before.booking_rules, confirm_within_hours: 4 };
    expect((await settings.setBookingRules(rules)).page.booking_rules.confirm_within_hours).toBe(4);
    await settings.setBookingRules(before.booking_rules);
  });

  it('фото и аватар, скрыть и открыть страницу', async () => {
    const settings = new HttpMasterSettingsGateway(await signedIn());
    const png = new Blob([new Uint8Array([137, 80, 78, 71])], { type: 'image/png' });
    const withPhoto = await settings.addPhoto(png, 'Чистка');
    const photo = withPhoto.page.photos.at(-1)!;
    expect(photo.alt).toBe('Чистка');
    await expect(settings.addPhoto(new Blob(['hi'], { type: 'text/plain' }))).rejects.toMatchObject(
      { status: 422, code: 'invalid_photo' },
    );
    expect((await settings.removePhoto(photo.id)).page.photos).not.toContainEqual(photo);
    expect((await settings.setAvatar(png)).page.avatar_url).toBeTruthy();
    expect((await settings.removeAvatar()).page.avatar_url).toBeNull();

    const page = new HttpMasterGateway(new HttpCore({ origin: ORIGIN }));
    expect((await settings.unpublish()).status).toBe('draft');
    await expect(page.getPage(DEMO_SLUG)).rejects.toMatchObject({ status: 404 });
    expect((await settings.publish()).status).toBe('published');
    await expect(page.getPage(DEMO_SLUG)).resolves.toMatchObject({ slug: DEMO_SLUG });
  });
});

describe('админ-панель', () => {
  it('вход, CSRF, мастер, блокировка клиента, журнал', async () => {
    const admin = new HttpAdminGateway(new HttpCore({ origin: ORIGIN }));
    await expect(admin.login(MOCK_ADMIN_LOGIN, 'wrong-password')).rejects.toMatchObject({
      status: 401,
      code: 'invalid_credentials',
    });
    const session = await admin.login(MOCK_ADMIN_LOGIN, MOCK_ADMIN_PASSWORD);
    expect(session.admin.login).toBe(MOCK_ADMIN_LOGIN);
    expect((await admin.me())?.csrf_token).toBe(session.csrf_token);

    const created = await admin.createMaster({
      slug: 'asem',
      display_name: 'Әсем Нурланова',
      name_forms: { nominative: 'Әсем', genitive: 'Әсем', dative: 'Әсем' },
      specialty: 'Массаж',
      timezone: 'Asia/Almaty',
      owner_phone: '+77010001122',
    });
    expect([created.status, created.agent, created.publish_blockers.length]).toEqual([
      'draft',
      'not_connected',
      2,
    ]);
    await expect(admin.setPublication(created.id, true)).rejects.toMatchObject({ status: 409 });
    expect((await admin.masters({ q: 'asem' })).map((m) => m.slug)).toEqual(['asem']);

    const alisa = (await admin.masters({ q: DEMO_SLUG }))[0]!;
    expect((await admin.setPublication(alisa.id, false)).status).toBe('draft');
    expect((await admin.setPublication(alisa.id, true)).status).toBe('published');

    const { items } = await admin.clients({ q: '7011231234' });
    const blocked = await admin.setClientBlock(items[0]!.id, true, 'Спам');
    expect([blocked.blocked, blocked.blocked_reason]).toEqual([true, 'Спам']);
    await admin.setClientBlock(items[0]!.id, false);

    const audit = await admin.audit();
    expect(audit.items.slice(0, 2).map((e) => e.action)).toEqual([
      'client.unblocked',
      'client.blocked',
    ]);

    await admin.logout();
    expect(await admin.me()).toBeNull();
    await expect(admin.dashboard()).rejects.toMatchObject({ status: 401 });
  });
});
