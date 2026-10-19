import '@beauty/ui/styles.css';
import './app/global.css';
import { StrictMode } from 'react';
import { HttpAdminGateway, HttpCore } from '@beauty/api';
import { createRoot } from 'react-dom/client';
import { App } from './app/App';

async function bootstrap(): Promise<void> {
  // mock — весь API отвечают моки в странице (вход: owner / beauty-admin-2026).
  let fetch: ((request: Request) => Promise<Response>) | undefined;
  if (import.meta.env.VITE_API_MODE !== 'real') {
    const { createMockFetch } = await import('@beauty/mocks/browser');
    fetch = createMockFetch({ real: new Set() });
  }
  const admin = new HttpAdminGateway(new HttpCore(fetch ? { fetch } : {}));
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App container={{ admin }} />
    </StrictMode>,
  );
}

void bootstrap();
