import type { Page } from '@playwright/test';

export const CLIENT = 'http://alisa.localhost:5173';
export const MASTER = 'http://localhost:5174';
export const ADMIN = 'http://localhost:5175';

/** Скриншот экрана 390×844 для сверки с макетами (docs/design/mockups). */
export async function shot(page: Page, name: string): Promise<void> {
  // Дать шрифтам и анимациям устояться; каретку и мигание — убрать.
  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({ content: '*{caret-color:transparent!important}' });
  await page.waitForTimeout(300);
  await page.screenshot({ path: `screenshots/${name}.png`, animations: 'disabled' });
}
