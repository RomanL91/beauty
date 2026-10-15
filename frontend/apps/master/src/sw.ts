/// <reference lib="webworker" />
import { setupServiceWorker } from '@beauty/pwa/sw';

declare const self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: Array<{ url: string; revision: string | null }>;
};

setupServiceWorker(self.__WB_MANIFEST, { defaultTitle: 'Кабинет' });
