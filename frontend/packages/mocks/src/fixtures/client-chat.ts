import type { Appointment, Message } from '@beauty/api';
import { at, fromNow, humanDate, nextWeekday } from '../clock';
import { SERVICES } from './master-page';
import { ME_CLIENT } from './people';
import { base, bookingCard, slotFor, slotOffer, text, voice } from './messages';

/** Переписка клиента из макета «Чат с администратором». */
export const CLIENT_CONVERSATION_ID = '0192a0c0-0000-7000-8000-000000000201';

const minutesAgo = (m: number): string => fromNow(-m * 60_000);

/** Источник «памятка мастера» — базовый URL страницы мастера. */
export const AFTER_MASSAGE_NOTE = {
  title: 'Памятка Алисы «После массажа»',
  url: 'https://alisa.beautiful.kz/notes/after-massage',
};

/** История чата клиента: запрос → окна → выбор → заявка → голосовое → ответ с источниками. */
export function clientChatSeed(): { messages: Message[]; appointment: Appointment } {
  const friday = nextWeekday(4);
  const service = SERVICES.backMassage;
  const slots = ['12:00', '15:30', '18:00'].map((hm) => slotFor(service, at(friday, hm)));
  const chosen = slots[0]!;
  const appointment: Appointment = {
    id: '0192a0c0-0000-7000-8000-000000000301',
    status: 'requested',
    service,
    start: chosen.start,
    end: chosen.end,
    client: ME_CLIENT,
    hold_until: fromNow(100 * 60_000),
    auto_decline_at: fromNow(100 * 60_000),
  };
  const messages: Message[] = [
    text(
      base('client', minutesAgo(30)),
      'Здравствуйте! Хочу на массаж спины в пятницу, есть время?',
    ),
    slotOffer(
      base('agent', minutesAgo(29)),
      `Здравствуйте, Дарья! В ${humanDate(friday)}, на классический массаж спины (40 мин) свободно:`,
      slots,
      chosen.start,
    ),
    text(base('client', minutesAgo(28)), '12:00'),
    bookingCard(base('agent', minutesAgo(28)), appointment),
    voice(
      base('client', minutesAgo(26)),
      7,
      'А после массажа можно в бассейн?',
      '/mock-media/voice-7.wav',
    ),
    text(
      base('agent', minutesAgo(25), {
        sources: [
          AFTER_MASSAGE_NOTE,
          { title: 'Внешний источник (пример)', url: 'https://beautiful.kz/help/sources' },
        ],
      }),
      'Обычно советуют подождать пару часов — так написано и в памятке Алисы. Если есть вопросы по здоровью, могу передать их Алисе лично.',
    ),
  ];
  return { messages, appointment };
}
