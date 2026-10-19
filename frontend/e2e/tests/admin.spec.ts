import { expect, test, type Page } from '@playwright/test';
import { ADMIN, shot as screenshot } from './support';

// Панель — рабочее место хозяина: экран ноутбука.
test.use({
  viewport: { width: 1280, height: 860 },
  deviceScaleFactor: 1,
  isMobile: false,
  hasTouch: false,
});

async function shot(page: Page, name: string): Promise<void> {
  await expect(page.locator('[aria-live="polite"] > div')).toHaveCount(0, { timeout: 6000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await screenshot(page, name);
}

async function signIn(page: Page): Promise<void> {
  await page.goto(`${ADMIN}/masters`);
  await expect(page).toHaveURL(/\/login\?return=%2Fmasters/);
  await page.getByRole('textbox', { name: 'Логин' }).fill('owner');
  await page.getByLabel('Пароль').fill('wrong-password');
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page.getByText('Неверный логин или пароль')).toBeVisible();
  await page.getByLabel('Пароль').fill('beauty-admin-2026');
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page).toHaveURL(`${ADMIN}/masters`);
}

test('панель: вход, сводка, мастер — завести, карточка, публикация', async ({ page }) => {
  await page.goto(`${ADMIN}/login`);
  await screenshot(page, 'admin-login');
  await signIn(page);
  await expect(page.getByRole('link', { name: 'Алиса Мельникова' })).toBeVisible();
  await shot(page, 'admin-masters');

  await page.getByRole('link', { name: 'Сводка' }).click();
  await expect(page.getByText('Заявки на запись')).toBeVisible();
  await page.getByRole('img', { name: /Заявки на запись/ }).hover({ position: { x: 300, y: 80 } });
  await shot(page, 'admin-dashboard');

  await page.getByRole('link', { name: 'Мастера' }).click();
  await page.getByRole('button', { name: 'Завести мастера' }).click();
  const sheet = page.getByRole('dialog', { name: 'Новый мастер' });
  await sheet.getByRole('textbox', { name: 'Имя на странице' }).fill('Әсем Нурланова');
  await expect(sheet.getByRole('textbox', { name: 'Адрес страницы' })).toHaveValue('asem');
  await sheet.getByRole('button', { name: 'Завести мастера' }).click();
  await expect(sheet.getByText('Нужно агенту: «нет Даны»')).toBeVisible();
  await sheet.getByRole('textbox', { name: 'Кого? (нет …)' }).fill('Әсем');
  await sheet.getByRole('textbox', { name: 'Кому? (к …)' }).fill('Әсем');
  await sheet.getByRole('textbox', { name: 'Специализация' }).fill('Массаж лица');
  await sheet.getByRole('textbox', { name: 'Телефон владельца' }).fill('8 701 000 11 22');
  await screenshot(page, 'admin-new-master');
  await sheet.getByRole('button', { name: 'Завести мастера' }).click();

  await expect(page.getByRole('heading', { name: 'Әсем Нурланова' })).toBeVisible();
  await expect(page.getByText('Кабинет открыт номеру +7 701 000 11 22')).toBeVisible();
  await expect(page.getByText(/Опубликовать пока нельзя/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Опубликовать' })).toBeDisabled();
  await expect(page.getByText('beauty agent provision asem')).toBeVisible();
  await shot(page, 'admin-master');

  await page.getByRole('link', { name: 'К мастерам' }).click();
  await page.getByRole('link', { name: 'Алиса Мельникова' }).click();
  await page.getByRole('button', { name: 'Скрыть страницу' }).click();
  await expect(page.getByRole('button', { name: 'Опубликовать' })).toBeEnabled();
  await page.getByRole('button', { name: 'Выключить' }).click();
  await expect(page.getByRole('button', { name: 'Включить' })).toBeVisible();
});

test('панель: клиент — блокировка; администраторы; журнал; система', async ({ page }) => {
  await signIn(page);
  await page.getByRole('link', { name: 'Клиенты' }).click();
  await page.getByRole('searchbox', { name: 'Поиск по телефону' }).fill('701 123');
  const row = page.getByRole('row', { name: /\+7 701 123 12 34/ });
  await row.getByRole('button', { name: 'Заблокировать' }).click();
  await page
    .getByRole('dialog')
    .getByRole('textbox', { name: /Причина/ })
    .fill('Спам в чате');
  await page.getByRole('dialog').getByRole('button', { name: 'Заблокировать' }).click();
  await expect(page.getByText('Клиент заблокирован — его сессии закрыты')).toBeVisible();
  await expect(row.getByText('Заблокирован')).toBeVisible();
  await page.getByRole('searchbox', { name: 'Поиск по телефону' }).fill('');
  await shot(page, 'admin-clients');

  await page.getByRole('link', { name: 'ИИ-администратор' }).click();
  await expect(page.getByText('Последние сбои')).toBeVisible();
  await shot(page, 'admin-agent');

  await page.getByRole('link', { name: 'Администраторы' }).click();
  await page.getByRole('button', { name: 'Добавить' }).click();
  const sheet = page.getByRole('dialog', { name: 'Новый администратор' });
  await sheet.getByRole('textbox', { name: 'Логин' }).fill('manager');
  await sheet.getByRole('textbox', { name: 'Имя' }).fill('Менеджер');
  await sheet.getByLabel('Пароль').fill('manager-password-1');
  await sheet.getByRole('button', { name: 'Добавить' }).click();
  await expect(page.getByRole('row', { name: /Менеджер/ })).toBeVisible();
  await page
    .getByRole('row', { name: /Менеджер/ })
    .getByRole('button', { name: 'Отключить' })
    .click();
  await expect(page.getByRole('row', { name: /Менеджер/ }).getByText('Отключён')).toBeVisible();
  await shot(page, 'admin-admins');

  await page.getByRole('link', { name: 'Журнал' }).click();
  await expect(page.getByRole('cell', { name: 'Блокировка' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Новый администратор' })).toBeVisible();
  await shot(page, 'admin-audit');

  await page.getByRole('link', { name: 'Система' }).click();
  await expect(page.getByText('Пусто — всё отправлено')).toBeVisible();
  await shot(page, 'admin-system');

  await page.getByRole('button', { name: 'Выйти' }).click();
  await expect(page).toHaveURL(/\/login/);
});

test('панель на телефоне', async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();
  await signIn(page);
  await page.getByRole('link', { name: 'Сводка' }).click();
  await expect(page.getByText('Заявки на запись')).toBeVisible();
  await shot(page, 'admin-mobile');
  await context.close();
});
