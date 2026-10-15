import { createBrowserRouter, Navigate, type RouteObject } from 'react-router';
import { ChatPage, ChatSkeleton } from '../pages/chat/ChatPage';
import { LoginPage } from '../pages/login/LoginPage';
import { MainPage } from '../pages/main/MainPage';
import { RequireSession } from './RequireSession';
import { RootLayout } from './RootLayout';
import { RouteError } from './RouteError';

/** Маршруты клиента (см. README макетов). */
export const routes: RouteObject[] = [
  {
    element: <RootLayout />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <MainPage /> },
      { path: 'login', element: <LoginPage /> },
      {
        path: 'chat',
        element: (
          <RequireSession fallback={<ChatSkeleton />}>
            <ChatPage />
          </RequireSession>
        ),
      },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
];

export const createRouter = () => createBrowserRouter(routes);
