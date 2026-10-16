/**
 * Адаптеры `@beauty/api` против MSW-обработчиков: проверяем, что адаптеры
 * и моки говорят на одном контракте, и сценарии моков работают.
 */
import {
  ApiError,
  HttpAssistantGateway,
  HttpAuthGateway,
  HttpConversationGateway,
  HttpCore,
  HttpInboxGateway,
  HttpMasterEventsGateway,
  HttpMasterGateway,
  HttpScheduleGateway,
  StubMasterAuthGateway,
  type ChallengeStatus,
  type ConversationEvent,
  type MasterEvent,
  type MessageOf,
} from '@beauty/api';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { CONVERSATIONS, DARYA_REQUEST_ID, DEMO_SLUG } from './index';
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
