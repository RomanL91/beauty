import { expect, test } from '@playwright/test';
import { CLIENT, shot } from './support';

test('(а) клиент: страница → «Записаться» → вход → чат → выбор окна → карточка заявки', async ({
  page,
}) => {
  await page.goto(CLIENT);
  await expect(page.getByRole('heading', { name: 'Алиса Мельникова' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Ближайшие окна' })).toBeVisible();
  await expect(
    page.getByRole('link', { name: /^(Сегодня|Завтра|Пн|Вт|Ср|Чт|Пт|Сб|Вс) \d\d:\d\d$/ }).first(),
  ).toBeVisible();
  await shot(page, 'client-main');

  await page.getByRole('link', { name: 'Записаться', exact: true }).click();
  await expect(page).toHaveURL(/\/login\?return=/);
  await expect(page.getByRole('heading', { name: 'Вход через Telegram' })).toBeVisible();
  await expect(page.getByText('Запись к Алисе')).toBeVisible();
  await expect(page.getByText(/^\d{2}$/)).toBeVisible();
  await expect(page.getByRole('link', { name: 'Открыть Telegram' })).toHaveAttribute(
    'href',
    /^https:\/\/t\.me\//,
  );
  await shot(page, 'client-login');

  // MSW «подтверждает» вход в боте: pending → claimed → confirmed → completed → обмен.
  await expect(page).toHaveURL(/\/chat$/, { timeout: 15_000 });
  await expect(page.getByText('Хочу записаться. Какое время свободно?')).toBeVisible();

  const offer = page.getByRole('group', { name: 'Свободное время' }).last();
  await expect(offer.getByRole('button').first()).toBeEnabled({ timeout: 10_000 });
  const time = (await offer.getByRole('button').first().textContent())?.trim() ?? '';
  await offer.getByRole('button', { name: time }).click();

  await expect(page.getByText(`Ждёт подтверждения Алисы`).last()).toBeVisible();
  const card = page.locator('[id^="appointment-"]').last();
  await expect(card).toContainText(time);
  await expect(card.getByRole('button', { name: 'Перенести' })).toBeVisible();
  await expect(card).toContainText('Время держим за вами');
  await page.getByRole('log').evaluate((el) => el.parentElement?.scrollTo(0, 0));
  await shot(page, 'client-chat');
});

test('клиент: история чата — «Ответ ИИ», источники и голосовое', async ({ page }) => {
  await page.goto(CLIENT);
  await page.getByRole('link', { name: 'Написать' }).click();
  await expect(page).toHaveURL(/\/chat$/, { timeout: 15_000 });
  await expect(page.getByText('Источники').first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Памятка Алисы «После массажа»' })).toBeVisible();
  await expect(page.getByText(/Ответ ИИ · \d\d:\d\d/).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Воспроизвести голосовое' }).first()).toBeVisible();
});
