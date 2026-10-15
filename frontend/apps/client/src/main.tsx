import '@beauty/ui/styles.css';
import { StrictMode } from 'react';
import { HttpCore } from '@beauty/api';
import { registerPwa } from '@beauty/pwa/register';
import { createRoot } from 'react-dom/client';
import { App } from './app/App';
import { createClientContainer } from './app/container';
import { readEnv } from './shared/config/env';
import { MasterSlugResolver } from './shared/config/master-slug';

async function bootstrap(): Promise<void> {
  const env = readEnv();
  // Моки в странице для всего, чего ещё нет на бэкенде (см. AppEnv.realApi).
  let fetch: ((request: Request) => Promise<Response>) | undefined;
  if (env.realApi.trim() !== 'all') {
    const [{ createMockFetch }, { parseGroups }] = await Promise.all([
      import('@beauty/mocks/browser'),
      import('@beauty/mocks'),
    ]);
    fetch = createMockFetch({ real: parseGroups(env.realApi) });
  }
  const slug = MasterSlugResolver.forEnvironment({
    dev: import.meta.env.DEV,
    defaultMaster: env.defaultMaster,
  }).resolve(window.location);
  const container = createClientContainer(env, slug, new HttpCore(fetch ? { fetch } : {}));
  registerPwa({ enabled: import.meta.env.PROD });
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App container={container} />
    </StrictMode>,
  );
}

void bootstrap();
