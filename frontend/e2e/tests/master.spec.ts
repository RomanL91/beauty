import { expect, test } from '@playwright/test';
import { MASTER, shot } from './support';

test('(б) мастер: график → подтвердить заявку', async ({ page }) => {
  await page.goto(`${MASTER}/schedule`);
  const request = page.locator('li', { hasText: 'Заявка' });
  await expect(request).toContainText('Дарья К.');
  await expect(request.getByRole('timer')).toHaveText(
    /автоотклонение через (1 ч 40 мин|1 ч 39 мин)/,
  );
  await expect(page.getByText('1 заявка ждёт вас')).toBeVisible();
  await shot(page, 'master-schedule');

  await request.getByRole('button', { name: 'Подтвердить' }).click();
  await expect(page.getByText('Запись подтверждена — клиент получит уведомление')).toBeVisible();
  await expect(page.locator('li', { hasText: 'Заявка' })).toHaveCount(0);
  await expect(page.getByText('1 заявка ждёт вас')).toHaveCount(0);
  await expect(page.locator('li', { hasText: 'Дарья К.' })).toBeVisible();
});

test('(в) мастер: чаты → диалог → «Я» → отправка', async ({ page }) => {
  await page.goto(`${MASTER}/chats`);
  await expect(page.getByRole('tab', { name: 'Нужны вы · 2' })).toBeVisible();
  await expect(page.getByText('Нужны вы · заявка')).toBeVisible();
  await shot(page, 'master-chats');

  await page.getByRole('link', { name: /Новый клиент/ }).click();
  await expect(page.getByText('Заметка агента · видите только вы')).toBeVisible();
  await page.getByRole('link', { name: 'К чатам' }).click();
  await page.getByRole('link', { name: /Дарья К\./ }).click();
  await expect(page.getByRole('button', { name: 'Агент' })).toHaveAttribute('aria-pressed', 'true');
  await expect(
    page.getByText('Агент отвечает сам. Если напишете вы — он встанет на паузу.'),
  ).toBeVisible();
  await expect(page.getByText('Заявка · держим слот')).toBeVisible();
  await shot(page, 'master-dialog');

  await page.getByRole('button', { name: 'Я', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Я', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(
    page.getByText('Агент на паузе и молчит, пока вы не вернёте ему диалог.'),
  ).toBeVisible();

  await page
    .getByRole('textbox', { name: 'Ответ от вашего имени' })
    .fill('Дарья, жду вас в 12:00!');
  await page.getByRole('button', { name: 'Отправить' }).click();
  await expect(page.getByText('Дарья, жду вас в 12:00!')).toBeVisible();
  await expect(page.getByText(/^Вы · \d\d:\d\d$/).last()).toBeVisible();

  // Вернуть агенту и снова ответить: ответ мастера сам переводит на «Я» с уведомлением.
  await page.getByRole('button', { name: 'Агент' }).click();
  await expect(page.getByRole('button', { name: 'Агент' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('textbox', { name: 'Ответ от вашего имени' }).fill('Если что — пишите');
  await page.keyboard.press('Enter');
  await expect(page.getByText('Диалог теперь ведёте вы — агент на паузе')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Я', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});

test('(г) мастер: поручение → выбор варианта → прогресс', async ({ page }) => {
  await page.goto(`${MASTER}/assistant`);
  await expect(page.getByText('Делаю перестановку')).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Предложить Оксане 15:00, Дарью — на 12:00' }),
  ).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('log').evaluate((el) => el.parentElement?.scrollTo(0, 0));
  await shot(page, 'master-assistant');

  await page.getByRole('button', { name: 'Закрой воскресенье' }).click();
  const yes = page.getByRole('button', { name: 'Да, закрыть' });
  await expect(yes).toBeVisible();
  await yes.click();
  await expect(yes).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('Выполняю')).toBeVisible();
  await expect(page.getByText('Готово', { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('Всё сделал.')).toBeVisible();
});

test('мастер: голосовое поручение удержанием большой кнопки', async ({ page }) => {
  await page.goto(`${MASTER}/assistant`);
  const mic = page.getByRole('button', { name: 'Удерживайте и говорите' });
  const box = await mic.boundingBox();
  if (!box) throw new Error('нет кнопки');
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await expect(page.getByText('← влево — отмена')).toBeVisible();
  await page.waitForTimeout(1500);
  await page.mouse.up();
  await page.getByRole('button', { name: 'Отправить голосовое' }).click();
  await expect(page.getByText('«Закрой воскресенье»')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole('button', { name: 'Да, закрыть' })).toBeVisible();
});
