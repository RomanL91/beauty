import { expect, test, type Page } from '@playwright/test';
import { MASTER, shot as screenshot } from './support';

/** Скриншот без тостов от прошлых сохранений. */
async function shot(page: Page, name: string, top = true): Promise<void> {
  await expect(page.locator('[aria-live="polite"] > div')).toHaveCount(0, { timeout: 6000 });
  if (top) await page.evaluate(() => window.scrollTo(0, 0));
  await screenshot(page, name);
}

test('мастер: клиенты — поиск, карточка, имя, заметки', async ({ page }) => {
  await page.goto(`${MASTER}/clients`);
  const list = page.getByRole('list', { name: 'Клиенты' });
  await expect(list.getByRole('link', { name: /Дарья К\./ })).toBeVisible();
  await expect(list.getByRole('link', { name: /Дарья К\..*2 заметки/ })).toBeVisible();
  await shot(page, 'master-clients');

  await page.getByRole('tab', { name: 'С записью' }).click();
  await expect(list.getByRole('link').filter({ hasNotText: 'Впереди' })).toHaveCount(0);
  await expect(list.getByRole('link')).not.toHaveCount(0);
  await page.getByRole('tab', { name: 'Все' }).click();

  // Новый клиент без имени: поиск по цифрам телефона → карточка → имя.
  await page.getByRole('searchbox', { name: 'Поиск клиентов' }).fill('12 34');
  await expect(list.getByRole('link')).toHaveCount(1);
  await list.getByRole('link', { name: /Новый клиент · …12 34/ }).click();
  await expect(page.getByRole('heading', { name: 'Новый клиент · …12 34' })).toBeVisible();
  await page.getByRole('button', { name: 'Дать имя' }).click();
  const sheet = page.getByRole('dialog', { name: 'Имя клиента' });
  await sheet.getByRole('textbox', { name: 'Как зовут клиента' }).fill('Сауле');
  await sheet.getByRole('button', { name: 'Сохранить' }).click();
  await expect(page.getByText('Имя сохранено')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Сауле' })).toBeVisible();

  // Заметка: добавить, повтор не дублирует, удалить.
  const notes = page.getByRole('list', { name: 'Заметки о клиенте' });
  const field = page.getByRole('textbox', { name: 'Новая заметка' });
  await field.fill('Аллергия на лаванду');
  await page.getByRole('button', { name: 'Добавить заметку' }).click();
  await expect(notes.getByRole('listitem')).toHaveCount(1);
  await expect(field).toHaveValue('');
  await field.fill('аллергия на лаванду');
  await page.getByRole('button', { name: 'Добавить заметку' }).click();
  await expect(field).toHaveValue('');
  await expect(notes.getByRole('listitem')).toHaveCount(1);
  await page.getByRole('button', { name: 'Удалить заметку «Аллергия на лаванду»' }).click();
  await expect(page.getByText('Заметка удалена')).toBeVisible();
  await expect(notes).toHaveCount(0);

  // Имя видно в чатах; из переписки — обратно в карточку.
  await page.getByRole('link', { name: 'Написать' }).click();
  await expect(page).toHaveURL(/\/chats\//);
  await expect(page.getByText('Сауле').first()).toBeVisible();
  await page.goBack();
  await page.getByRole('link', { name: 'К клиентам' }).click();
  await page.getByRole('searchbox', { name: 'Поиск клиентов' }).fill('');
  await list.getByRole('link', { name: /Дарья К\./ }).click();
  await expect(page.getByText('Аллергия на лаванду — масла без неё')).toBeVisible();
  await expect(page.getByText('ИИ-администратор').first()).toBeVisible();
  // Сегодняшняя заявка к полудню уходит в историю — считаем только прошедшие визиты.
  await expect(
    page
      .getByRole('list', { name: 'История визитов' })
      .getByRole('listitem')
      .filter({ hasText: 'Был' }),
  ).toHaveCount(2);
  await shot(page, 'master-client-card');
});
