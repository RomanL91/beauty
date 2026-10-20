import type { MasterPage, Service } from '@beauty/api';
import { workPhotoDataUrl } from '../audio';
import { MASTER_TIMEZONE } from '../clock';

/** Slug мастера из макетов. */
export const DEMO_SLUG = 'alisa';

const tenge = (amount: number): Service['price'] => ({ amount: amount * 100, currency: 'KZT' });

/** Услуги из макета «Страница мастера» (цены — плейсхолдеры для демо). */
export const SERVICES = {
  backMassage: {
    id: '0192a0c0-0000-7000-8000-000000000501',
    title: 'Классический массаж спины',
    description: 'Снимает напряжение в спине и шее после сидячей работы.',
    duration_min: 40,
    price: tenge(9000),
  },
  antiCellulite: {
    id: '0192a0c0-0000-7000-8000-000000000502',
    title: 'Антицеллюлитный массаж',
    description:
      'Интенсивный ручной массаж бёдер, ягодиц и живота; курс — 10 процедур через день. ' +
      'Не делаю при беременности, варикозе, воспалениях кожи и в первые дни цикла.',
    duration_min: 60,
    price: tenge(12000),
  },
  facial: {
    id: '0192a0c0-0000-7000-8000-000000000503',
    title: 'Чистка лица комбинированная',
    description: 'Ультразвук и ручная чистка, маска и успокаивающий уход.',
    duration_min: 90,
    price: tenge(15000),
  },
  care: {
    id: '0192a0c0-0000-7000-8000-000000000504',
    title: 'Уходовая процедура',
    description: '',
    duration_min: 60,
    price: tenge(11000),
  },
} satisfies Record<string, Service>;

/** Публичная страница Алисы. */
export function masterPage(): MasterPage {
  return {
    slug: DEMO_SLUG,
    display_name: 'Алиса Мельникова',
    name_forms: { nominative: 'Алиса', genitive: 'Алисы', dative: 'Алисе' },
    specialty: 'Косметолог · массаж',
    address: 'Астана, ул. Кенесары, 40',
    timezone: MASTER_TIMEZONE,
    avatar_url: null,
    about:
      'Восемь лет работаю с лицом и телом. Начинаю с короткой консультации: что беспокоит, ' +
      'какой результат нужен, есть ли противопоказания. Подбираю процедуру под задачу, а не ' +
      'под прайс. Работаю в отдельном кабинете, одноразовые расходники.',
    services: Object.values(SERVICES),
    photos: Array.from({ length: 6 }, (_, i) => ({
      id: `0192a0c0-0000-7000-8000-00000000060${i}`,
      url: workPhotoDataUrl(i + 1),
      alt: `Работа ${i + 1}`,
    })),
    booking_rules: { confirm_within_hours: 2, change_deadline_hours: 12 },
  };
}
