import { VitePWA } from 'vite-plugin-pwa';

/** Манифест конкретного приложения. */
export interface PwaManifestOptions {
  readonly name: string;
  readonly shortName: string;
  readonly description: string;
  readonly startUrl: string;
}

/**
 * Плагин PWA для обоих приложений: свой service worker (`src/sw.ts`,
 * стратегия injectManifest), манифест с темой #7A2E57, precache сборки,
 * включая локальные шрифты. Регистрация — вручную (`@beauty/pwa/register`).
 */
export function beautyPwa(manifest: PwaManifestOptions) {
  return VitePWA({
    strategies: 'injectManifest',
    srcDir: 'src',
    filename: 'sw.ts',
    injectRegister: false,
    registerType: 'autoUpdate',
    manifest: {
      name: manifest.name,
      short_name: manifest.shortName,
      description: manifest.description,
      lang: 'ru',
      start_url: manifest.startUrl,
      scope: '/',
      display: 'standalone',
      orientation: 'portrait',
      theme_color: '#7A2E57',
      background_color: '#F4F3F0',
      icons: [
        { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
        { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
        {
          src: '/icons/icon-maskable-512.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: 'maskable',
        },
      ],
    },
    injectManifest: {
      globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
      globIgnores: ['mockServiceWorker.js', '**/*.map'],
      maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
    },
    devOptions: { enabled: false },
  });
}
