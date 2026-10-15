import react from '@vitejs/plugin-react';
import { beautyPwa } from '@beauty/pwa/vite';
import { defineConfig, loadEnv } from 'vite';

/**
 * Клиентское PWA. В dev открывается как `http://<slug>.localhost:5173`
 * (или `?master=<slug>`); `/api` проксируется на бэкенд.
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const api = env.VITE_API_PROXY || 'http://localhost:8000';
  const proxy = { '/api': { target: api, changeOrigin: false, ws: false } };
  return {
    plugins: [
      react(),
      beautyPwa({
        name: 'beautiful.kz — запись к мастеру',
        shortName: 'Запись',
        description: 'Страница мастера: запись и чат с администратором',
        startUrl: '/',
      }),
    ],
    server: { port: 5173, host: true, allowedHosts: ['.localhost', '.beautiful.kz'], proxy },
    preview: { port: 4173, host: true, allowedHosts: ['.localhost', '.beautiful.kz'], proxy },
    build: { target: 'es2022', sourcemap: true },
  };
});
