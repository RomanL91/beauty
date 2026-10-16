import { defineConfig, devices } from '@playwright/test';

/**
 * E2E на mock-режиме: оба приложения поднимаются dev-серверами с MSW
 * (включая мок входа через Telegram). Экран 390×844 — как в макетах.
 *
 * `PW_CHROMIUM_PATH` — свой Chromium (например, предустановленный в CI-образе).
 */
const executablePath = process.env.PW_CHROMIUM_PATH || undefined;

export default defineConfig({
  testDir: './tests',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    ...devices['Pixel 7'],
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    locale: 'ru-RU',
    timezoneId: 'Asia/Almaty',
    trace: 'retain-on-failure',
    launchOptions: {
      ...(executablePath && { executablePath }),
      // Системный язык браузера — русский: поля времени в 24-часовом формате, как у мастеров.
      env: { ...process.env, LANG: 'ru_RU.UTF-8', LANGUAGE: 'ru' },
      args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
    },
  },
  projects: [{ name: 'mobile-chromium', use: { browserName: 'chromium' } }],
  webServer: [
    {
      command: 'pnpm --filter @beauty/client exec vite --port 5173 --strictPort',
      url: 'http://localhost:5173',
      env: { VITE_API_MODE: 'mock', VITE_MOCK_AUTH: '1' },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: 'pnpm --filter @beauty/master exec vite --port 5174 --strictPort',
      url: 'http://localhost:5174',
      env: { VITE_API_MODE: 'mock' },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
