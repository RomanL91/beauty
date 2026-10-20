import { expect, test, type Page } from '@playwright/test';
import { MASTER, shot as screenshot } from './support';

/** Скриншот без тостов от прошлых действий. */
async function shot(page: Page, name: string, top = true): Promise<void> {
  await expect(page.locator('[aria-live="polite"] > div')).toHaveCount(0, { timeout: 8000 });
  if (top) await page.evaluate(() => window.scrollTo(0, 0));
  await screenshot(page, name);
}

test('мастер: новая услуга → ассистент расспрашивает → ответ — в «Что знает ассистент»', async ({
  page,
}) => {
  await page.goto(`${MASTER}/settings/services`);
  await page.getByRole('button', { name: 'Добавить услугу' }).click();
  const sheet = page.getByRole('dialog', { name: 'Новая услуга' });
  await sheet.getByRole('textbox', { name: 'Название' }).fill('Ботокс');
  await sheet.getByRole('combobox', { name: 'Длительность' }).selectOption('30');
  await sheet.getByRole('textbox', { name: 'Цена, ₸' }).fill('40 000');
  await sheet.getByRole('button', { name: 'Добавить' }).click();
  await expect(page.getByText('Услуга добавлена')).toBeVisible();

  await page.getByRole('link', { name: 'К настройкам' }).click();
  await page.getByRole('link', { name: 'Поручить агенту' }).click();
  await expect(page.getByText(/Добавили «Ботокс»/)).toBeVisible({ timeout: 10_000 });
  await page
    .getByRole('group', { name: 'Варианты' })
    .last()
    .getByRole('button', { name: 'Только в определённые дни' })
    .click();
  await expect(page.getByText(/В какие именно дни/)).toBeVisible();
  await page
    .getByRole('textbox', { name: 'Поручение текстом' })
    .fill('По пятницам, до четырёх человек подряд — ампула вскрывается одна');
  await page.getByRole('button', { name: 'Отправить поручение' }).click();
  await expect(page.getByText(/Запомнил для «Ботокс»/)).toBeVisible();
  await screenshot(page, 'master-assistant-interview');

  await page.getByRole('link', { name: 'К графику' }).click();
  await page.getByRole('link', { name: 'Настройки' }).click();
  await page.getByRole('link', { name: /Ассистент/ }).click();
  const botox = page.getByRole('list', { name: 'Ботокс' });
  await expect(botox).toContainText('По пятницам, до четырёх человек подряд');
  await expect(botox).toContainText('ИИ');
});

test('мастер: «Ассистент» — записывать сразу, своя запись опыта, правка и удаление', async ({
  page,
}) => {
  await page.goto(`${MASTER}/settings`);
  await page.getByRole('link', { name: /Ассистент/ }).click();
  await expect(page.getByRole('heading', { name: 'Ассистент', exact: true })).toBeVisible();
  const general = page.getByRole('list', { name: 'Как вы работаете' });
  await expect(general).toContainText('Сложные массажи — с утра');

  const autonomy = page.getByRole('switch', { name: 'Записывать клиентов сразу' });
  await expect(autonomy).not.toBeChecked();
  await autonomy.check();
  await expect(page.getByText(/Ассистент сам подтверждает запись/)).toBeVisible();

  await page.getByRole('button', { name: 'Добавить' }).click();
  const sheet = page.getByRole('dialog', { name: 'Новая запись' });
  await sheet
    .getByRole('textbox', { name: 'Что важно знать' })
    .fill('Постоянным клиентам можно поставить на 20:00 — задержусь');
  await sheet.getByRole('button', { name: 'Сохранить' }).click();
  await expect(page.getByText('Ассистент запомнил')).toBeVisible();
  await expect(general).toContainText('Постоянным клиентам можно поставить на 20:00');
  await shot(page, 'master-settings-assistant');

  await general.getByRole('button', { name: /Изменить: Постоянным/ }).click();
  const edit = page.getByRole('dialog', { name: 'Запись опыта' });
  await edit.getByRole('textbox', { name: 'Что важно знать' }).fill('Постоянным — можно до 20:30');
  await edit.getByRole('button', { name: 'Сохранить' }).click();
  await expect(general).toContainText('Постоянным — можно до 20:30');
  await general.getByRole('button', { name: /Удалить: Постоянным/ }).click();
  await expect(general).not.toContainText('Постоянным');

  await page.getByRole('link', { name: 'К настройкам' }).click();
  await expect(page.getByRole('link', { name: /Ассистент/ })).toContainText('Записывает сразу');
});
