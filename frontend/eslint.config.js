import js from '@eslint/js';
import { defineConfig, globalIgnores } from 'eslint/config';
import prettier from 'eslint-config-prettier';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default defineConfig([
  globalIgnores([
    '**/dist',
    '**/dev-dist',
    '**/node_modules',
    '**/schema.d.ts',
    '**/mockServiceWorker.js',
    'e2e/screenshots',
    'e2e/playwright-report',
    'e2e/test-results',
    '**/*.tmp.mjs',
  ]),
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: { globals: { ...globals.browser } },
    rules: {
      '@typescript-eslint/consistent-type-imports': 'error',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      eqeqeq: ['error', 'always'],
    },
  },
  {
    files: ['apps/**/*.{ts,tsx}', 'packages/ui/**/*.{ts,tsx}'],
    extends: [reactHooks.configs.flat['recommended-latest']],
  },
  {
    files: ['apps/*/src/**/*.tsx'],
    extends: [reactRefresh.configs.vite],
  },
  {
    files: ['**/*.config.{ts,js}', 'e2e/**/*.ts', 'apps/*/src/sw.ts'],
    languageOptions: { globals: { ...globals.node, ...globals.serviceworker } },
  },
  prettier,
]);
