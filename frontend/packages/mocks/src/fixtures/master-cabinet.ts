import type {
  Appointment,
  ClientRef,
  ConversationSummary,
  Message,
  MessageOf,
  Service,
} from '@beauty/api';
import { addDays, at, fromNow, localDate, plusMinutes, weekday } from '../clock';
import { SERVICES } from './master-page';
import { CLIENTS } from './people';
import { agentNote, base, bookingCard, slotFor, text, voice } from './messages';
import { AFTER_MASSAGE_NOTE } from './client-chat';

/** Переписки мастера (id совпадают в списке и графике). */
export const CONVERSATIONS = {
  darya: '0192a0c0-0000-7000-8000-000000000211',
  newcomer: '0192a0c0-0000-7000-8000-000000000212',
  marina: '0192a0c0-0000-7000-8000-000000000213',
  irina: '0192a0c0-0000-7000-8000-000000000214',
  oksana: '0192a0c0-0000-7000-8000-000000000215',
  aigerim: '0192a0c0-0000-7000-8000-000000000216',
} as const;

/** Заявка Дарьи из макетов «График» и «Диалог». */
export const DARYA_REQUEST_ID = '0192a0c0-0000-7000-8000-000000000311';

/** Рабочий день мастера. */
export const WORKING_HOURS = { start: '10:00', end: '19:00' } as const;

/** Перерыв в демо-дне. */
export interface BreakEntry {
  readonly date: string;
  readonly start: string;
  readonly end: string;
  readonly title: string;
}

const minutesAgo = (m: number): string => fromNow(-m * 60_000);

function confirmed(
  id: string,
  client: ClientRef,
  service: Service,
  start: string,
  extra: { note?: string; reminder?: 'none' | 'sent' | 'read'; end?: string } = {},
): Appointment {
  return {
    id,
    status: 'confirmed',
    service,
    start,
    end: extra.end ?? plusMinutes(start, service.duration_min),
    client,
    confirmed_at: minutesAgo(60 * 24),
    reminder: extra.reminder ?? 'none',
    ...(extra.note !== undefined && { note: extra.note }),
  };
}

/** Записи недели: демо-день — сегодня (как в макете «График дня»), остальные дни — легче. */
export function appointmentsSeed(): { appointments: Appointment[]; breaks: BreakEntry[] } {
  const today = localDate(0);
  const appointments: Appointment[] = [
    confirmed(
      '0192a0c0-0000-7000-8000-000000000321',
      CLIENTS.oksana,
      SERVICES.facial,
      at(today, '10:00'),
      {
        reminder: 'read',
      },
    ),
    {
      id: DARYA_REQUEST_ID,
      status: 'requested',
      service: SERVICES.backMassage,
      start: at(today, '12:00'),
      end: at(today, '12:40'),
      client: CLIENTS.darya,
      hold_until: fromNow(100 * 60_000),
      auto_decline_at: fromNow(100 * 60_000),
    },
    confirmed(
      '0192a0c0-0000-7000-8000-000000000322',
      CLIENTS.marina,
      SERVICES.antiCellulite,
      at(today, '14:00'),
    ),
    confirmed(
      '0192a0c0-0000-7000-8000-000000000323',
      CLIENTS.aigerim,
      SERVICES.care,
      at(today, '15:30'),
      {
        note: 'перенесена агентом с четверга',
      },
    ),
  ];
  const breaks: BreakEntry[] = [{ date: today, start: '15:00', end: '15:30', title: 'Перерыв' }];

  // Остальные будни недели — по одной-две записи, чтобы перелистывание было живым.
  const filler: Array<[ClientRef, Service, string]> = [
    [CLIENTS.irina, SERVICES.care, '11:00'],
    [CLIENTS.marina, SERVICES.backMassage, '16:00'],
  ];
  for (let offset = -6; offset <= 6; offset += 1) {
    const date = addDays(today, offset);
    if (offset === 0 || weekday(date) === 6) continue;
    filler.forEach(([client, service, hm], i) => {
      if ((offset + i) % 2 === 0) {
        appointments.push(
          confirmed(
            `0192a0c0-0000-7000-8000-0000000004${String(offset + 10).padStart(2, '0')}${i}`,
            client,
            service,
            at(date, hm),
          ),
        );
      }
    });
  }
  return { appointments, breaks };
}

/** Выходной (воскресенье). */
export const isDayOff = (date: string): boolean => weekday(date) === 6;

/** Список чатов из макета «Все чаты». */
export function inboxSeed(): ConversationSummary[] {
  return [
    {
      id: CONVERSATIONS.darya,
      client: CLIENTS.darya,
      handler: 'agent',
      needs_me: 'request',
      last_message: {
        author: 'agent',
        preview: 'Заявка на пт 12:00 ждёт подтверждения',
        created_at: minutesAgo(40),
      },
      unread: 1,
    },
    {
      id: CONVERSATIONS.newcomer,
      client: CLIENTS.newcomer,
      handler: 'agent',
      needs_me: 'question',
      last_message: {
        author: 'agent',
        preview: 'Просит скидку за подругу — агент передал вам',
        created_at: minutesAgo(63),
      },
      unread: 1,
    },
    {
      id: CONVERSATIONS.marina,
      client: CLIENTS.marina,
      handler: 'agent',
      needs_me: null,
      last_message: {
        author: 'agent',
        preview: 'Предложил субботу 11:00, ждём ответа',
        created_at: minutesAgo(110),
      },
      unread: 0,
    },
    {
      id: CONVERSATIONS.irina,
      client: CLIENTS.irina,
      handler: 'master',
      needs_me: null,
      last_message: {
        author: 'master',
        preview: 'Хорошо, жду вас в субботу',
        created_at: minutesAgo(60 * 20),
      },
      unread: 0,
    },
    {
      id: CONVERSATIONS.oksana,
      client: CLIENTS.oksana,
      handler: 'agent',
      needs_me: null,
      last_message: {
        author: 'agent',
        preview: 'Напомнил о записи в пт 10:00',
        created_at: minutesAgo(60 * 22),
      },
      unread: 0,
    },
    {
      id: CONVERSATIONS.aigerim,
      client: CLIENTS.aigerim,
      handler: 'agent',
      needs_me: null,
      last_message: {
        author: 'agent',
        preview: 'Перенос на пт 15:30 подтверждён',
        created_at: minutesAgo(60 * 44),
      },
      unread: 0,
    },
  ];
}

/** История диалога с Дарьей из макета «Диалог и пульт агента». */
export function daryaDialogSeed(request: Appointment): Message[] {
  const offerTimes = ['12:00', '15:30', '18:00'];
  return [
    text(
      base('client', minutesAgo(45)),
      'Здравствуйте! Хочу на массаж спины в пятницу, есть время?',
    ),
    text(
      base('agent', minutesAgo(44)),
      `Здравствуйте, Дарья! В пятницу свободно ${offerTimes.slice(0, -1).join(', ')} и ${offerTimes.at(-1)}.`,
    ),
    text(base('client', minutesAgo(43)), '12:00'),
    bookingCard(base('agent', minutesAgo(42)), request),
    voice(
      base('client', minutesAgo(41)),
      7,
      'А после массажа можно в бассейн?',
      '/mock-media/voice-7.wav',
    ),
    text(
      base('agent', minutesAgo(40), {
        sources: [{ ...AFTER_MASSAGE_NOTE, title: 'После массажа' }],
      }),
      'Обычно советуют подождать пару часов — так написано и в памятке Алисы.',
    ),
    agentNote(
      base('agent', minutesAgo(40)),
      'Дарья третий раз выбирает обеденное время. Записал в карточку: «удобно 12–14».',
    ),
  ];
}

/** Короткие истории остальных диалогов. */
export function otherDialogsSeed(): Record<string, Message[]> {
  return {
    [CONVERSATIONS.newcomer]: [
      text(
        base('client', minutesAgo(65)),
        'Добрый день! Мы с подругой хотим вдвоём на чистку, будет скидка?',
      ),
      text(
        base('agent', minutesAgo(64)),
        'Здравствуйте! Про скидки решает Алиса — я передал ей ваш вопрос, она ответит здесь.',
      ),
      agentNote(
        base('agent', minutesAgo(63)),
        'Скидок за подругу в правилах нет — решите сами, агент не обещал.',
      ),
    ],
    [CONVERSATIONS.marina]: [
      text(base('client', minutesAgo(115)), 'Можно перенести антицеллюлитный на выходные?'),
      text(base('agent', minutesAgo(110)), 'Могу предложить субботу 11:00. Подходит?'),
    ],
    [CONVERSATIONS.irina]: [
      text(
        base('client', minutesAgo(60 * 20 + 5)),
        'Алиса, я приду в субботу, как договаривались?',
      ),
      text(base('master', minutesAgo(60 * 20), { ai: false }), 'Хорошо, жду вас в субботу'),
    ],
    [CONVERSATIONS.oksana]: [
      text(
        base('agent', minutesAgo(60 * 22)),
        'Оксана, напоминаю: завтра в 10:00 чистка лица у Алисы. До встречи!',
      ),
    ],
    [CONVERSATIONS.aigerim]: [
      text(
        base('client', minutesAgo(60 * 45)),
        'Можно перенести с четверга на пятницу после обеда?',
      ),
      text(base('agent', minutesAgo(60 * 44)), 'Готово: перенос на пт 15:30 подтверждён.'),
    ],
  };
}

/** Лента поручений из макета «Поручение голосом». */
export function assistantSeed(): Message[] {
  const choose1: MessageOf<'choice'> = {
    ...base('agent', minutesAgo(9)),
    kind: 'choice',
    choice_id: '0192a0c0-0000-7000-8000-000000000701',
    text: 'Дарья с телефоном на …89 67?',
    options: [
      { id: 'yes', label: 'Да, она' },
      { id: 'other', label: 'Другая Дарья' },
    ],
    selected_option_id: 'yes',
  };
  const choose2: MessageOf<'choice'> = {
    ...base('agent', minutesAgo(8)),
    kind: 'choice',
    choice_id: '0192a0c0-0000-7000-8000-000000000702',
    text: 'В субботу в 12:00 уже записана **Оксана Л.** — чистка лица до 13:30.',
    detail: 'У Оксаны в карточке: «удобно после обеда». Свободно 15:00–16:30.',
    options: [
      { id: 'swap', label: 'Предложить Оксане 15:00, Дарью — на 12:00' },
      { id: 'later', label: 'Записать Дарью на 15:00' },
      { id: 'none', label: 'Ничего не менять', tone: 'muted' },
    ],
    selected_option_id: 'swap',
  };
  const progress: MessageOf<'task_progress'> = {
    ...base('agent', minutesAgo(7)),
    kind: 'task_progress',
    task_id: '0192a0c0-0000-7000-8000-000000000711',
    title: 'Делаю перестановку',
    steps: [
      { id: 'hold', label: 'Слот 15:00 придержан для Оксаны', state: 'done' },
      { id: 'offer', label: 'Оксане отправлено предложение · ждём ответа', state: 'waiting' },
      { id: 'book', label: 'Записать Дарью на 12:00 и сообщить ей', state: 'pending' },
    ],
    footnote: 'Если Оксана откажется или не ответит до 18:00 — ничего не меняю и пишу вам.',
  };
  return [
    voice(
      base('master', minutesAgo(10), { ai: false }),
      4,
      'Запиши Дарью на массаж в субботу на двенадцать',
      '/mock-media/voice-4.wav',
    ),
    choose1,
    choose2,
    progress,
  ];
}

/** Окно для услуги (реэкспорт для сценариев). */
export { slotFor };
