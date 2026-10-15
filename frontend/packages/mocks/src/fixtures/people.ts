import type { ClientRef } from '@beauty/api';

/** Клиенты мастера из макетов. */
export const CLIENTS = {
  darya: {
    id: '0192a0c0-0000-7000-8000-000000000101',
    display_name: 'Дарья К.',
    phone_masked: '+7 705 ••• 89 67',
    visit_number: 3,
  },
  newcomer: {
    id: '0192a0c0-0000-7000-8000-000000000102',
    display_name: 'Новый клиент · …12 34',
    phone_masked: '+7 701 ••• 12 34',
    visit_number: 1,
  },
  marina: {
    id: '0192a0c0-0000-7000-8000-000000000103',
    display_name: 'Марина С.',
    phone_masked: '+7 707 ••• 45 10',
    visit_number: 5,
  },
  irina: {
    id: '0192a0c0-0000-7000-8000-000000000104',
    display_name: 'Ирина П.',
    phone_masked: '+7 702 ••• 77 21',
    visit_number: 2,
  },
  oksana: {
    id: '0192a0c0-0000-7000-8000-000000000105',
    display_name: 'Оксана Л.',
    phone_masked: '+7 705 ••• 30 08',
    visit_number: 7,
  },
  aigerim: {
    id: '0192a0c0-0000-7000-8000-000000000106',
    display_name: 'Айгерим Т.',
    phone_masked: '+7 708 ••• 61 93',
    visit_number: 4,
  },
} satisfies Record<string, ClientRef>;

/** Клиент «я» в клиентском приложении (Дарья). */
export const ME_CLIENT: ClientRef = CLIENTS.darya;
