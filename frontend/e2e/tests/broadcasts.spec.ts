import { expect, test, type Page } from '@playwright/test';
import { ADMIN, CLIENT, MASTER, shot as screenshot } from './support';

/** Скриншот без тостов от прошлых действий. */
async function shot(page: Page, name: string, top = true): Promise<void> {
  await expect(page.locator('[aria-live="polite"] > div')).toHaveCount(0, { timeout: 8000 });
  if (top) await page.evaluate(() => window.scrollTo(0, 0));
  await screenshot(page, name);
}

// PNG 1×1 — настоящий файл с сигнатурой формата.
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
  'base64',
);

test('мастер: рассылка с фото всем клиентам; лимит на сутки', async ({ page }) => {
  await page.goto(`${MASTER}/clients`);
  await page.getByRole('link', { name: 'Рассылка' }).click();
  await expect(page.getByRole('heading', { name: 'Рассылка' })).toBeVisible();
  const history = page.getByRole('list', { name: 'Отправленные рассылки' });
  await expect(history.getByRole('listitem')).toHaveCount(1);

  await page
    .getByRole('textbox', { name: 'Текст объявления' })
    .fill('С 1 ноября — массаж лица! Первую неделю −20%. Записывайтесь в чате.');
  await page.getByLabel('Файл фото для объявления').setInputFiles({
    name: 'sale.png',
    mimeType: 'image/png',
    buffer: PNG,
  });
  await expect(page.getByRole('img', { name: 'Фото объявления' })).toBeVisible();
  await shot(page, 'master-broadcast');

  await page.getByRole('button', { name: /^Отправить \d+ клиентам$/ }).click();
  const sheet = page.getByRole('dialog', { name: 'Отправить рассылку?' });
  await expect(sheet).toContainText('Отменить отправку будет нельзя');
  await sheet.getByRole('button', { name: 'Да, отправить' }).click();
  await expect(page.getByText('Рассылка отправляется')).toBeVisible();
  await expect(history.getByRole('listitem')).toHaveCount(2);
  await expect(history.getByRole('listitem').first()).toContainText(/Отправлено \d+ клиентам/, {
    timeout: 10_000,
  });
  await expect(history.getByRole('listitem').first()).toContainText('с фото');
  await expect(page.getByText(/Не чаще одной рассылки в сутки/)).toBeVisible();
  await expect(page.getByRole('button', { name: /^Отправить \d+ клиентам$/ })).toBeDisabled();

  // Объявление — в чатах мастера.
  await page.getByRole('link', { name: 'К клиентам' }).click();
  await page.getByRole('link', { name: 'Чаты' }).click();
  await expect(page.getByText(/Вы: Объявление: С 1 ноября/).first()).toBeVisible();
});

test('мастер: «Разошли всем…» — агент готовит черновик, отправляет мастер', async ({ page }) => {
  await page.goto(`${MASTER}/assistant`);
  await page
    .getByRole('textbox', { name: 'Поручение текстом' })
    .fill('Разошли всем: с 1 ноября массаж лица, первую неделю −20%');
  await page.getByRole('button', { name: 'Отправить поручение' }).click();
  const card = page.getByRole('group', { name: 'Черновик рассылки' });
  await expect(card).toContainText('С 1 ноября массаж лица, первую неделю −20%');
  await expect(page.getByText(/сама разослать не могу/)).toBeVisible();
  await card.getByLabel('Файл фото для объявления').setInputFiles({
    name: 'sale.png',
    mimeType: 'image/png',
    buffer: PNG,
  });
  await expect(page.getByText('Фото добавлено')).toBeVisible();
  await card.getByRole('button', { name: /^Отправить \d+ клиентам$/ }).click();
  await card.getByRole('button', { name: 'Да, отправить' }).click();
  await expect(card).toContainText(/Отправлено \d+ клиентам/, { timeout: 10_000 });
  await expect(page.getByText('Рассылка отправляется')).toHaveCount(0, { timeout: 8000 });
  await card.scrollIntoViewIfNeeded();
  await screenshot(page, 'master-assistant-broadcast');
});

test('клиент: объявление мастера в чате', async ({ page }) => {
  await page.goto(CLIENT);
  await page.getByRole('link', { name: 'Написать' }).click();
  await expect(page).toHaveURL(/\/chat$/, { timeout: 15_000 });
  const announcement = page.getByText('Объявление от Алисы');
  await announcement.scrollIntoViewIfNeeded();
  await expect(announcement).toBeVisible();
  await expect(page.getByText(/Открыла запись на ноябрь!/)).toBeVisible();
});

test('админ: запрет рассылок мастеру', async ({ page }) => {
  await page.goto(ADMIN);
  await page.getByRole('textbox', { name: 'Логин' }).fill('owner');
  await page.getByLabel('Пароль').fill('beauty-admin-2026');
  await page.getByRole('button', { name: 'Войти' }).click();
  await page.getByRole('link', { name: 'Мастера' }).click();
  await page.getByRole('link', { name: 'Алиса Мельникова' }).click();
  const card = page.getByRole('region', { name: 'Рассылки' });
  await expect(card).toContainText('Открыла запись на ноябрь!');
  await card.getByRole('button', { name: 'Запретить рассылки' }).click();
  await expect(card.getByRole('button', { name: 'Разрешить рассылки' })).toBeVisible();
  await expect(card).toContainText('Запрещены');
});
