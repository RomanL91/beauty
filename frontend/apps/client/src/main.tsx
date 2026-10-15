import '@beauty/ui/styles.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './app/App';
import { createClientContainer } from './app/container';
import { readEnv } from './shared/config/env';
import { MasterSlugResolver } from './shared/config/master-slug';

async function bootstrap(): Promise<void> {
  const env = readEnv();
  if (import.meta.env.VITE_API_MODE === 'mock') {
    const { startMockWorker } = await import('@beauty/mocks/browser');
    await startMockWorker({ auth: env.mockAuth });
  }
  const slug = MasterSlugResolver.forEnvironment({
    dev: import.meta.env.DEV,
    defaultMaster: env.defaultMaster,
  }).resolve(window.location);
  const container = createClientContainer(env, slug);
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App container={container} />
    </StrictMode>,
  );
}

void bootstrap();
