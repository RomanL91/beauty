import { expect, test, type Page } from '@playwright/test';
import { MASTER, shot as screenshot } from './support';

/** Скриншот экрана с начала, без тостов от прошлых сохранений. */
async function shot(page: Page, name: string, top = true): Promise<void> {
  await expect(page.locator('[aria-live="polite"] > div')).toHaveCount(0, { timeout: 6000 });
  if (top) await page.evaluate(() => window.scrollTo(0, 0));
  await screenshot(page, name);
}

// Моки живут в странице: переходы — внутри приложения, без перезагрузки.

test('мастер: настройки — профиль, услуга, график, публикация', async ({ page }) => {
  await page.goto(`${MASTER}/settings`);
  await expect(page.getByText('Опубликована')).toBeVisible();
  await expect(page.getByRole('link', { name: /Услуги.*4 услуги/ })).toBeVisible();
  await shot(page, 'master-settings');

  // Профиль: правка «о себе» сохраняется и видна после возврата.
  await page.getByRole('link', { name: /Профиль/ }).click();
  const about = page.getByRole('textbox', { name: 'О себе' });
  await expect(about).toBeVisible();
  await expect(page.getByRole('button', { name: 'Сохранить' })).toBeDisabled();
  await page.getByRole('textbox', { name: 'Кому? (к …)' }).fill('');
  await page.getByRole('button', { name: 'Сохранить' }).click();
  await expect(page.getByText('Нужно для сообщений агента')).toBeVisible();
  await page.getByRole('textbox', { name: 'Кому? (к …)' }).fill('Алисе');
  await about.fill('Работаю с лицом и телом десять лет.');
  await shot(page, 'master-settings-profile');
  await page.getByRole('button', { name: 'Сохранить' }).click();
  await expect(page.getByText('Профиль сохранён')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Сохранить' })).toBeDisabled();
  await page.getByRole('link', { name: 'К настройкам' }).click();

  // Услуги: добавить с ценой в тенге, ошибка цены — у поля.
  await page.getByRole('link', { name: /Услуги/ }).click();
  await page.getByRole('button', { name: 'Добавить услугу' }).click();
  const sheet = page.getByRole('dialog', { name: 'Новая услуга' });
  await sheet.getByRole('textbox', { name: 'Название' }).fill('Массаж лица');
  await sheet.getByRole('combobox', { name: 'Длительность' }).selectOption('45');
  await sheet.getByRole('textbox', { name: 'Цена, ₸' }).fill('дорого');
  await sheet.getByRole('button', { name: 'Добавить' }).click();
  await expect(sheet.getByText('Сумма в тенге, например 12000')).toBeVisible();
  await sheet.getByRole('textbox', { name: 'Цена, ₸' }).fill('10 000');
  await sheet
    .getByRole('textbox', { name: 'Описание' })
    .fill('Лимфодренаж и лифтинг. Не делаю при розацеа и свежем ботоксе.');
  await shot(page, 'master-settings-service', false);
  await sheet.getByRole('button', { name: 'Добавить' }).click();
  await expect(page.getByText('Услуга добавлена')).toBeVisible();
  await expect(page.getByRole('button', { name: /Массаж лица.*45 мин · 10\s000 ₸/ })).toBeVisible();
  await shot(page, 'master-settings-services');
  await page.getByRole('link', { name: 'К настройкам' }).click();

  // График: перерыв в понедельник, пересечение — ошибка у дня, воскресенье — рабочее.
  await page.getByRole('link', { name: /График и выходные/ }).click();
  await page.getByRole('button', { name: '+ Перерыв и ещё интервал' }).first().click();
  await page.getByLabel('Понедельник: конец интервала 1').fill('14:00');
  await page.getByLabel('Понедельник: начало интервала 2').fill('13:00');
  await expect(page.getByText('Интервалы пересекаются')).toBeVisible();
  await page.getByLabel('Понедельник: начало интервала 2').fill('15:00');
  await page.getByLabel('Понедельник: конец интервала 2').fill('19:00');
  await expect(page.getByText('Интервалы пересекаются')).toHaveCount(0);
  await page.getByRole('switch', { name: 'Воскресенье — выходной' }).check();
  await shot(page, 'master-settings-hours');
  await page.getByRole('button', { name: 'Сохранить' }).click();
  await expect(page.getByText('График сохранён')).toBeVisible();
  await page.getByRole('link', { name: 'К настройкам' }).click();
  await expect(page.getByRole('link', { name: /Пн, Вт, Ср, Чт, Пт, Сб, Вс/ })).toBeVisible();

  // Правила записи.
  await page.getByRole('link', { name: /Правила записи/ }).click();
  await page.getByRole('combobox', { name: 'Подтвердить заявку в течение' }).selectOption('4');
  await shot(page, 'master-settings-rules');
  await page.getByRole('button', { name: 'Сохранить' }).click();
  await expect(page.getByText('Правила сохранены')).toBeVisible();
  await page.getByRole('link', { name: 'К настройкам' }).click();
  await expect(page.getByRole('link', { name: /Подтверждение за 4 ч/ })).toBeVisible();

  // Скрыть и снова опубликовать.
  await page.getByRole('button', { name: 'Скрыть' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Скрыть страницу' }).click();
  await expect(page.getByText('Черновик')).toBeVisible();
  await page.getByRole('button', { name: 'Опубликовать' }).click();
  await expect(page.getByText('Страница открыта — клиенты могут записываться')).toBeVisible();
  await expect(page.getByText('Опубликована')).toBeVisible();
});

test('мастер: фото работ — загрузка и удаление', async ({ page }) => {
  await page.goto(`${MASTER}/settings/photos`);
  await expect(page.getByRole('img', { name: 'Работа 1' })).toBeVisible();
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
    'base64',
  );
  await page
    .getByLabel('Файлы фото работ')
    .setInputFiles([{ name: 'work.png', mimeType: 'image/png', buffer: png }]);
  await expect(page.getByText('7 из 30', { exact: false })).toBeVisible();
  await page
    .getByLabel('Файлы фото работ')
    .setInputFiles([{ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('hi') }]);
  await expect(page.getByText('Нужна картинка JPEG, PNG или WebP')).toBeVisible();
  await shot(page, 'master-settings-photos');
  await page.getByRole('button', { name: 'Убрать фото 7' }).click();
  await expect(page.getByText('Фото убрано')).toBeVisible();
  await expect(page.getByText('6 из 30', { exact: false })).toBeVisible();
});
