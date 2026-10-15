import { defineConfig } from 'vitest/config';

/** Unit-тесты всего workspace: пакеты — в Node, приложения — в jsdom. */
export default defineConfig({
  test: {
    projects: [
      {
        test: {
          name: 'packages',
          environment: 'node',
          include: ['packages/*/src/**/*.test.ts'],
        },
      },
      'apps/*/vitest.config.ts',
    ],
  },
});
