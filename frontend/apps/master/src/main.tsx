import '@beauty/ui/styles.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './app/App';
import { createMasterContainer } from './app/container';
import { readEnv } from './shared/config/env';

async function bootstrap(): Promise<void> {
  const env = readEnv();
  if (import.meta.env.VITE_API_MODE === 'mock') {
    const { startMockWorker } = await import('@beauty/mocks/browser');
    await startMockWorker({ auth: true });
  }
  const container = createMasterContainer(env);
  // Итерация 1: сессия мастера — заглушка, открывается сразу (до первых запросов).
  await container.auth.restoreSession();
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App container={container} />
    </StrictMode>,
  );
}

void bootstrap();
