import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

/** PWA мастера (дашборд). В dev — `http://localhost:5174`; `/api` проксируется на бэкенд. */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const api = env.VITE_API_PROXY || 'http://localhost:8000';
  const proxy = { '/api': { target: api, changeOrigin: false, ws: false } };
  return {
    plugins: [react()],
    server: { port: 5174, host: true, allowedHosts: ['.localhost', '.beautiful.kz'], proxy },
    preview: { port: 4174, host: true, allowedHosts: ['.localhost', '.beautiful.kz'], proxy },
    build: { target: 'es2022', sourcemap: true },
  };
});
